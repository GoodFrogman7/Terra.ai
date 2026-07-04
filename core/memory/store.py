"""
SQLite-based persistent storage for chat sessions and long-term memory.
Provides ChatGPT-style chat history and memory capabilities.
"""
import sqlite3
import json
import uuid
import os
import logging
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from contextlib import contextmanager

# Configure debug logging
logger = logging.getLogger("memory_store")
logger.setLevel(logging.DEBUG if os.getenv("MEMORY_DEBUG", "").lower() == "true" else logging.INFO)

# Default database path
DEFAULT_DB_PATH = Path(os.getenv("MEMORY_DB_PATH", "data/memory/memory.db"))


def _ensure_db_dir(db_path: Path):
    """Ensure the database directory exists."""
    db_path.parent.mkdir(parents=True, exist_ok=True)


DEFAULT_USER_ID = "local"


def _ensure_user_id_column(conn, table: str):
    """Migration guard: add user_id to pre-multi-tenancy databases."""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if "user_id" not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT NOT NULL DEFAULT '{DEFAULT_USER_ID}'")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_user_id ON {table}(user_id)")


class ChatStore:
    """
    Persistent store for chat sessions.
    Each chat has:
    - chat_id: unique identifier
    - title: auto-generated from first user message
    - messages: list of {role, content, timestamp, metadata}
    - created_at, updated_at: timestamps
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        _ensure_db_dir(self.db_path)
        self._init_db()
        logger.debug(f"[CHAT_STORE] Initialized with db_path={self.db_path}")

    @contextmanager
    def _get_conn(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT 'New Chat',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT 'local'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    metadata TEXT,
                    FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id)")
            _ensure_user_id_column(conn, "chats")
            conn.commit()

    def create_chat(self, title: str = "New Chat", user_id: str = DEFAULT_USER_ID) -> str:
        """Create a new chat session. Returns chat_id."""
        chat_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO chats (chat_id, title, created_at, updated_at, user_id) VALUES (?, ?, ?, ?, ?)",
                (chat_id, title, now, now, user_id)
            )
            conn.commit()
        logger.debug(f"[CHAT_STORE] Created chat: chat_id={chat_id}, title={title}, user_id={user_id}")
        return chat_id

    def add_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Add a message to a chat. Returns message id."""
        now = datetime.utcnow().isoformat()
        metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        with self._get_conn() as conn:
            cursor = conn.execute(
                "INSERT INTO messages (chat_id, role, content, timestamp, metadata) VALUES (?, ?, ?, ?, ?)",
                (chat_id, role, content, now, metadata_json)
            )
            conn.execute("UPDATE chats SET updated_at = ? WHERE chat_id = ?", (now, chat_id))
            conn.commit()
            msg_id = cursor.lastrowid
        logger.debug(f"[CHAT_STORE] Added message: chat_id={chat_id}, role={role}, msg_id={msg_id}")
        return msg_id

    def get_chat(self, chat_id: str, user_id: str = DEFAULT_USER_ID) -> Optional[Dict[str, Any]]:
        """Get a chat with all its messages (scoped to the owning user)."""
        with self._get_conn() as conn:
            chat_row = conn.execute(
                "SELECT * FROM chats WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
            ).fetchone()
            if not chat_row:
                return None
            
            messages = []
            for row in conn.execute(
                "SELECT * FROM messages WHERE chat_id = ? ORDER BY id ASC", (chat_id,)
            ):
                msg = {
                    "id": row["id"],
                    "role": row["role"],
                    "content": row["content"],
                    "timestamp": row["timestamp"],
                }
                if row["metadata"]:
                    msg["metadata"] = json.loads(row["metadata"])
                messages.append(msg)
            
            return {
                "chat_id": chat_row["chat_id"],
                "title": chat_row["title"],
                "created_at": chat_row["created_at"],
                "updated_at": chat_row["updated_at"],
                "messages": messages,
            }

    def get_messages(self, chat_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get messages for a chat, optionally limited to last N messages."""
        with self._get_conn() as conn:
            if limit:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
                    (chat_id, limit)
                ).fetchall()
                rows = list(reversed(rows))
            else:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE chat_id = ? ORDER BY id ASC",
                    (chat_id,)
                ).fetchall()
            
            messages = []
            for row in rows:
                msg = {
                    "id": row["id"],
                    "role": row["role"],
                    "content": row["content"],
                    "timestamp": row["timestamp"],
                }
                if row["metadata"]:
                    msg["metadata"] = json.loads(row["metadata"])
                messages.append(msg)
            return messages

    def list_chats(self, limit: int = 50, offset: int = 0, user_id: str = DEFAULT_USER_ID) -> List[Dict[str, Any]]:
        """List the user's chats, ordered by most recently updated."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM chats WHERE user_id = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (user_id, limit, offset)
            ).fetchall()
            return [
                {
                    "chat_id": row["chat_id"],
                    "title": row["title"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

    def update_title(self, chat_id: str, title: str):
        """Update chat title."""
        now = datetime.utcnow().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE chats SET title = ?, updated_at = ? WHERE chat_id = ?",
                (title, now, chat_id)
            )
            conn.commit()
        logger.debug(f"[CHAT_STORE] Updated title: chat_id={chat_id}, title={title}")

    def delete_chat(self, chat_id: str, user_id: str = DEFAULT_USER_ID):
        """Delete a chat and all its messages (only if owned by the user)."""
        with self._get_conn() as conn:
            owned = conn.execute(
                "SELECT 1 FROM chats WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
            ).fetchone()
            if not owned:
                return
            conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            conn.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
            conn.commit()
        logger.debug(f"[CHAT_STORE] Deleted chat: chat_id={chat_id}")

    def chat_exists(self, chat_id: str, user_id: str = DEFAULT_USER_ID) -> bool:
        """Check if a chat exists for this user."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM chats WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
            ).fetchone()
            return row is not None


class MemoryStore:
    """
    Long-term memory storage.
    Stores summarized facts, user preferences, and recurring topics
    that persist across chat sessions.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        _ensure_db_dir(self.db_path)
        self._init_db()
        logger.debug(f"[MEMORY_STORE] Initialized with db_path={self.db_path}")

    @contextmanager
    def _get_conn(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    memory_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL DEFAULT 'general',
                    content TEXT NOT NULL,
                    source_chat_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    importance INTEGER DEFAULT 1,
                    access_count INTEGER DEFAULT 0,
                    user_id TEXT NOT NULL DEFAULT 'local'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_summaries (
                    chat_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    topics TEXT,
                    created_at TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT 'local'
                )
            """)
            _ensure_user_id_column(conn, "memories")
            _ensure_user_id_column(conn, "chat_summaries")
            conn.commit()

    def add_memory(
        self,
        content: str,
        category: str = "general",
        source_chat_id: Optional[str] = None,
        importance: int = 1,
        user_id: str = DEFAULT_USER_ID
    ) -> str:
        """Add a new memory. Returns memory_id."""
        memory_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO memories
                   (memory_id, category, content, source_chat_id, created_at, updated_at, importance, user_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (memory_id, category, content, source_chat_id, now, now, importance, user_id)
            )
            conn.commit()
        logger.debug(f"[MEMORY_STORE] Added memory: memory_id={memory_id}, category={category}")
        return memory_id

    def get_memories(
        self,
        category: Optional[str] = None,
        limit: int = 20,
        user_id: str = DEFAULT_USER_ID
    ) -> List[Dict[str, Any]]:
        """Get the user's memories, optionally filtered by category."""
        with self._get_conn() as conn:
            if category:
                rows = conn.execute(
                    """SELECT * FROM memories WHERE user_id = ? AND category = ?
                       ORDER BY importance DESC, updated_at DESC LIMIT ?""",
                    (user_id, category, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM memories WHERE user_id = ?
                       ORDER BY importance DESC, updated_at DESC LIMIT ?""",
                    (user_id, limit)
                ).fetchall()
            
            # Update access count
            memory_ids = [row["memory_id"] for row in rows]
            if memory_ids:
                placeholders = ",".join("?" * len(memory_ids))
                conn.execute(
                    f"UPDATE memories SET access_count = access_count + 1 WHERE memory_id IN ({placeholders})",
                    memory_ids
                )
                conn.commit()
            
            logger.debug(f"[MEMORY_STORE] Retrieved {len(rows)} memories, ids={memory_ids}")
            
            return [
                {
                    "memory_id": row["memory_id"],
                    "category": row["category"],
                    "content": row["content"],
                    "source_chat_id": row["source_chat_id"],
                    "created_at": row["created_at"],
                    "importance": row["importance"],
                }
                for row in rows
            ]

    def update_memory(self, memory_id: str, content: str, importance: Optional[int] = None, user_id: str = DEFAULT_USER_ID):
        """Update a memory's content (only if owned by the user)."""
        now = datetime.utcnow().isoformat()
        with self._get_conn() as conn:
            if importance is not None:
                conn.execute(
                    "UPDATE memories SET content = ?, importance = ?, updated_at = ? WHERE memory_id = ? AND user_id = ?",
                    (content, importance, now, memory_id, user_id)
                )
            else:
                conn.execute(
                    "UPDATE memories SET content = ?, updated_at = ? WHERE memory_id = ? AND user_id = ?",
                    (content, now, memory_id, user_id)
                )
            conn.commit()
        logger.debug(f"[MEMORY_STORE] Updated memory: memory_id={memory_id}")

    def delete_memory(self, memory_id: str, user_id: str = DEFAULT_USER_ID):
        """Delete a memory (only if owned by the user)."""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM memories WHERE memory_id = ? AND user_id = ?", (memory_id, user_id))
            conn.commit()
        logger.debug(f"[MEMORY_STORE] Deleted memory: memory_id={memory_id}")

    def save_chat_summary(self, chat_id: str, summary: str, topics: List[str], user_id: str = DEFAULT_USER_ID):
        """Save a summarized version of a chat."""
        now = datetime.utcnow().isoformat()
        topics_json = json.dumps(topics, ensure_ascii=False)
        with self._get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO chat_summaries (chat_id, summary, topics, created_at, user_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (chat_id, summary, topics_json, now, user_id)
            )
            conn.commit()
        logger.debug(f"[MEMORY_STORE] Saved chat summary: chat_id={chat_id}")

    def get_chat_summary(self, chat_id: str, user_id: str = DEFAULT_USER_ID) -> Optional[Dict[str, Any]]:
        """Get a chat summary."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM chat_summaries WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
            ).fetchone()
            if not row:
                return None
            return {
                "chat_id": row["chat_id"],
                "summary": row["summary"],
                "topics": json.loads(row["topics"]) if row["topics"] else [],
                "created_at": row["created_at"],
            }

    def get_all_summaries(self, limit: int = 10, user_id: str = DEFAULT_USER_ID) -> List[Dict[str, Any]]:
        """Get the user's recent chat summaries for context."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM chat_summaries WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
            return [
                {
                    "chat_id": row["chat_id"],
                    "summary": row["summary"],
                    "topics": json.loads(row["topics"]) if row["topics"] else [],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]


# Singleton instances
_chat_store: Optional[ChatStore] = None
_memory_store: Optional[MemoryStore] = None
_chat_store_lock = threading.Lock()
_memory_store_lock = threading.Lock()


def get_chat_store() -> ChatStore:
    global _chat_store
    if _chat_store is None:
        with _chat_store_lock:
            if _chat_store is None:
                _chat_store = ChatStore()
    return _chat_store


def get_memory_store() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        with _memory_store_lock:
            if _memory_store is None:
                _memory_store = MemoryStore()
    return _memory_store

