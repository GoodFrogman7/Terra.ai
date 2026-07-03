"""
API routes for chat sessions and memory management.
These are ADDITIVE routes - they don't modify existing API behavior.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging
import os

from core.memory.store import get_chat_store, get_memory_store
from core.memory.context_builder import extract_title_from_message

logger = logging.getLogger("memory_routes")
logger.setLevel(logging.DEBUG if os.getenv("MEMORY_DEBUG", "").lower() == "true" else logging.INFO)

router = APIRouter(prefix="/memory", tags=["memory"])


# ============ Request/Response Models ============

class CreateChatRequest(BaseModel):
    title: Optional[str] = "New Chat"


class CreateChatResponse(BaseModel):
    chat_id: str
    title: str


class AddMessageRequest(BaseModel):
    role: str
    content: str
    metadata: Optional[Dict[str, Any]] = None


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    chat_id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[MessageResponse] = Field(default_factory=list)


class ChatListItem(BaseModel):
    chat_id: str
    title: str
    created_at: str
    updated_at: str


class ChatListResponse(BaseModel):
    chats: List[ChatListItem]
    total: int


class AddMemoryRequest(BaseModel):
    content: str
    category: str = "general"
    importance: int = 1


class MemoryResponse(BaseModel):
    memory_id: str
    category: str
    content: str
    created_at: str
    importance: int


class MemoryListResponse(BaseModel):
    memories: List[MemoryResponse]


class UpdateTitleRequest(BaseModel):
    title: str


# ============ Chat Session Routes ============

@router.post("/chats", response_model=CreateChatResponse)
def create_chat(req: CreateChatRequest):
    """Create a new chat session."""
    chat_store = get_chat_store()
    chat_id = chat_store.create_chat(title=req.title or "New Chat")
    logger.debug(f"[API] Created chat: chat_id={chat_id}")
    return CreateChatResponse(chat_id=chat_id, title=req.title or "New Chat")


@router.get("/chats", response_model=ChatListResponse)
def list_chats(limit: int = 50, offset: int = 0):
    """List all chat sessions, ordered by most recent."""
    chat_store = get_chat_store()
    chats = chat_store.list_chats(limit=limit, offset=offset)
    return ChatListResponse(
        chats=[ChatListItem(**c) for c in chats],
        total=len(chats)
    )


@router.get("/chats/{chat_id}", response_model=ChatResponse)
def get_chat(chat_id: str):
    """Get a specific chat with all messages."""
    chat_store = get_chat_store()
    chat = chat_store.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    messages = [
        MessageResponse(
            id=m["id"],
            role=m["role"],
            content=m["content"],
            timestamp=m["timestamp"],
            metadata=m.get("metadata")
        )
        for m in chat["messages"]
    ]
    
    return ChatResponse(
        chat_id=chat["chat_id"],
        title=chat["title"],
        created_at=chat["created_at"],
        updated_at=chat["updated_at"],
        messages=messages
    )


@router.post("/chats/{chat_id}/messages")
def add_message(chat_id: str, req: AddMessageRequest):
    """Add a message to a chat."""
    chat_store = get_chat_store()
    
    if not chat_store.chat_exists(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    
    msg_id = chat_store.add_message(
        chat_id=chat_id,
        role=req.role,
        content=req.content,
        metadata=req.metadata
    )
    
    # Auto-update title from first user message
    chat = chat_store.get_chat(chat_id)
    if chat and chat["title"] == "New Chat":
        user_messages = [m for m in chat["messages"] if m["role"] == "user"]
        if len(user_messages) == 1:
            title = extract_title_from_message(user_messages[0]["content"])
            chat_store.update_title(chat_id, title)
            logger.debug(f"[API] Auto-updated title: chat_id={chat_id}, title={title}")
    
    logger.debug(f"[API] Added message: chat_id={chat_id}, msg_id={msg_id}")
    return {"ok": True, "msg_id": msg_id}


@router.patch("/chats/{chat_id}")
def update_chat_title(chat_id: str, req: UpdateTitleRequest):
    """Update a chat's title."""
    chat_store = get_chat_store()
    
    if not chat_store.chat_exists(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat_store.update_title(chat_id, req.title)
    logger.debug(f"[API] Updated title: chat_id={chat_id}, title={req.title}")
    return {"ok": True}


@router.delete("/chats/{chat_id}")
def delete_chat(chat_id: str):
    """Delete a chat and all its messages."""
    chat_store = get_chat_store()
    
    if not chat_store.chat_exists(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat_store.delete_chat(chat_id)
    logger.debug(f"[API] Deleted chat: chat_id={chat_id}")
    return {"ok": True}


@router.get("/chats/{chat_id}/messages")
def get_messages(chat_id: str, limit: Optional[int] = None):
    """Get messages from a chat."""
    chat_store = get_chat_store()
    
    if not chat_store.chat_exists(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    
    messages = chat_store.get_messages(chat_id, limit=limit)
    return {
        "chat_id": chat_id,
        "messages": [
            MessageResponse(
                id=m["id"],
                role=m["role"],
                content=m["content"],
                timestamp=m["timestamp"],
                metadata=m.get("metadata")
            )
            for m in messages
        ]
    }


# ============ Long-term Memory Routes ============

@router.post("/memories", response_model=MemoryResponse)
def add_memory(req: AddMemoryRequest):
    """Add a new long-term memory."""
    memory_store = get_memory_store()
    memory_id = memory_store.add_memory(
        content=req.content,
        category=req.category,
        importance=req.importance
    )
    
    logger.debug(f"[API] Added memory: memory_id={memory_id}")
    
    return MemoryResponse(
        memory_id=memory_id,
        category=req.category,
        content=req.content,
        created_at="",  # Will be filled by store
        importance=req.importance
    )


@router.get("/memories", response_model=MemoryListResponse)
def list_memories(category: Optional[str] = None, limit: int = 20):
    """List long-term memories."""
    memory_store = get_memory_store()
    memories = memory_store.get_memories(category=category, limit=limit)
    
    return MemoryListResponse(
        memories=[
            MemoryResponse(
                memory_id=m["memory_id"],
                category=m["category"],
                content=m["content"],
                created_at=m["created_at"],
                importance=m["importance"]
            )
            for m in memories
        ]
    )


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str):
    """Delete a long-term memory."""
    memory_store = get_memory_store()
    memory_store.delete_memory(memory_id)
    logger.debug(f"[API] Deleted memory: memory_id={memory_id}")
    return {"ok": True}


# ============ Debug Route ============

@router.get("/debug/status")
def memory_debug_status():
    """Get memory system debug status."""
    if os.getenv("MEMORY_DEBUG", "").lower() != "true":
        return {"debug_enabled": False}
    
    chat_store = get_chat_store()
    memory_store = get_memory_store()
    
    chats = chat_store.list_chats(limit=100)
    memories = memory_store.get_memories(limit=100)
    
    return {
        "debug_enabled": True,
        "chat_count": len(chats),
        "memory_count": len(memories),
        "db_path": str(chat_store.db_path),
    }

