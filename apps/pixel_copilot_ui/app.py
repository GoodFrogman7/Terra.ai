import sys, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
import os, requests, json, re, html
from datetime import datetime
import streamlit as st
from core.graph.graph import graph_dot

API_BASE = os.getenv("COPILOT_API_BASE", "http://127.0.0.1:8000")

# ============ Memory/Chat API Helpers ============

def _api_create_chat(title: str = "New Chat") -> dict:
    """Create a new chat via API."""
    try:
        r = requests.post(f"{API_BASE}/memory/chats", json={"title": title}, timeout=10)
        if r.ok:
            return r.json()
    except Exception as e:
        st.error(f"Failed to create chat: {e}")
    return {}


def _api_list_chats(limit: int = 50) -> list:
    """List all chats from API."""
    try:
        r = requests.get(f"{API_BASE}/memory/chats", params={"limit": limit}, timeout=10)
        if r.ok:
            return r.json().get("chats", [])
    except Exception:
        pass
    return []


def _api_get_chat(chat_id: str) -> dict:
    """Get a chat by ID from API."""
    try:
        r = requests.get(f"{API_BASE}/memory/chats/{chat_id}", timeout=10)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return {}


def _api_add_message(chat_id: str, role: str, content: str, metadata: dict = None):
    """Add a message to a chat."""
    try:
        payload = {"role": role, "content": content}
        if metadata:
            payload["metadata"] = metadata
        r = requests.post(f"{API_BASE}/memory/chats/{chat_id}/messages", json=payload, timeout=10)
        return r.ok
    except Exception:
        return False


def _api_delete_chat(chat_id: str):
    """Delete a chat."""
    try:
        r = requests.delete(f"{API_BASE}/memory/chats/{chat_id}", timeout=10)
        return r.ok
    except Exception:
        return False


def _format_timestamp(ts: str) -> str:
    """Format timestamp for display."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        now = datetime.utcnow()
        diff = now - dt.replace(tzinfo=None)
        if diff.days == 0:
            return dt.strftime("%H:%M")
        elif diff.days == 1:
            return "Yesterday"
        elif diff.days < 7:
            return dt.strftime("%A")
        else:
            return dt.strftime("%b %d")
    except Exception:
        return ""

st.set_page_config(page_title="Customer Support Copilot v4", layout="wide")

# Initialize domain state
if "last_domain" not in st.session_state:
    st.session_state.last_domain = "pixel"

# Dynamic title based on agent mode
agent_titles = {
    "pixel": "Customer Support Copilot v4 (KB-first → Web fallback)",
    "finance": "Personal Finance Assistant (KB-first → Web fallback)",
    "healthcare": "Healthcare Assistant (KB-first → Web fallback)"
}
current_domain = st.session_state.get("last_domain", "pixel")
st.title(agent_titles[current_domain])


def _extract_topic(question: str) -> str:
    """Extract the core subject/topic from a question."""
    q = question.strip()
    q = re.sub(r'[?!.]+$', '', q)
    patterns = [
        r'^(what|how|why|when|where|who|whose|whom|which)\s+(is|are|was|were|do|does|did|can|could|would|will|should|has|have|had)\s+',
        r'^(what|how|why|when|where|who|whose|whom|which)\s+',
        r'^(can you|could you|do you|does|did you|will you|would you|please)\s+',
        r'^(is|are|was|were|do|does|did)\s+',
        r'^(tell me about|tell me|explain|show me|find|search|look up|give me|get me|i want to know about|i need)\s+',
        r'^(the|a|an)\s+',
    ]
    for pattern in patterns:
        q = re.sub(pattern, '', q, flags=re.IGNORECASE)
    q = re.sub(r'\s+', ' ', q).strip()
    topic = q.title() if q else "General"
    return topic[:30] + "..." if len(topic) > 30 else topic


def _build_context_prompt(history: list, current_query: str) -> str:
    """Build a context-aware query from conversation history."""
    if not history:
        return current_query
    
    q_lower = current_query.lower()
    is_followup = (
        len(current_query.split()) <= 6 or
        any(word in q_lower for word in ['he', 'she', 'it', 'they', 'that', 'this', 'there', 'him', 'her', 'his', 'their'])
    )
    
    if is_followup and len(history) >= 2:
        recent_context = []
        for msg in history[-4:]:
            if msg["role"] == "user":
                recent_context.append(f"Previous question: {msg['content']}")
            elif msg["role"] == "assistant":
                answer = re.sub(r'^\*\*\((KB|Web)\)\*\*\s*', '', msg["content"])
                first_sent = answer.split('.')[0] if '.' in answer else answer[:100]
                recent_context.append(f"Previous answer: {first_sent}")
        
        context_str = " | ".join(recent_context[-2:])
        return f"Context: [{context_str}] Current question: {current_query}"
    
    return current_query


# Initialize session states
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "all_chats" not in st.session_state:
    st.session_state.all_chats = []  # List of {"topic": str, "history": list}
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None
# NEW: Persistent chat ID for memory system
if "persistent_chat_id" not in st.session_state:
    st.session_state.persistent_chat_id = None
if "chat_list_cache" not in st.session_state:
    st.session_state.chat_list_cache = []
if "memory_enabled" not in st.session_state:
    st.session_state.memory_enabled = True


def get_current_topic():
    """Get topic from current chat history."""
    for msg in st.session_state.chat_history:
        if msg.get("role") == "user":
            return _extract_topic(msg.get("content", ""))
    return None


def save_current_chat():
    """Save current chat to all_chats."""
    if not st.session_state.chat_history:
        return
    
    topic = get_current_topic() or "Chat"
    chat_data = {"topic": topic, "history": st.session_state.chat_history.copy()}
    
    if st.session_state.current_chat_id is not None:
        # Update existing
        if st.session_state.current_chat_id < len(st.session_state.all_chats):
            st.session_state.all_chats[st.session_state.current_chat_id] = chat_data
    else:
        # Add new
        st.session_state.all_chats.append(chat_data)
        st.session_state.current_chat_id = len(st.session_state.all_chats) - 1


def load_chat(index: int):
    """Load a chat by index."""
    if 0 <= index < len(st.session_state.all_chats):
        chat = st.session_state.all_chats[index]
        st.session_state.chat_history = chat["history"].copy()
        st.session_state.current_chat_id = index


def new_chat():
    """Start a new chat."""
    save_current_chat()
    st.session_state.chat_history = []
    st.session_state.current_chat_id = None


# ============ NEW: Persistent Memory Functions ============

def start_new_persistent_chat():
    """Start a new persistent chat using the memory API."""
    if st.session_state.memory_enabled:
        result = _api_create_chat()
        if result.get("chat_id"):
            st.session_state.persistent_chat_id = result["chat_id"]
    st.session_state.chat_history = []
    st.session_state.current_chat_id = None
    # Refresh chat list
    st.session_state.chat_list_cache = _api_list_chats()


def load_persistent_chat(chat_id: str):
    """Load a persistent chat from memory API."""
    chat = _api_get_chat(chat_id)
    if chat:
        st.session_state.persistent_chat_id = chat_id
        # Convert API messages to session format
        st.session_state.chat_history = [
            {"role": m["role"], "content": m["content"]}
            for m in chat.get("messages", [])
        ]
        st.session_state.current_chat_id = None  # Not using old index system


def save_message_to_persistent(role: str, content: str, metadata: dict = None):
    """Save a message to persistent storage."""
    if st.session_state.memory_enabled and st.session_state.persistent_chat_id:
        _api_add_message(st.session_state.persistent_chat_id, role, content, metadata)


def delete_persistent_chat(chat_id: str):
    """Delete a persistent chat."""
    if _api_delete_chat(chat_id):
        if st.session_state.persistent_chat_id == chat_id:
            st.session_state.persistent_chat_id = None
            st.session_state.chat_history = []
        st.session_state.chat_list_cache = _api_list_chats()


# Sidebar with Chat List (ChatGPT-style)
with st.sidebar:
    # ============ NEW: Chat History Section ============
    st.markdown("""
    <style>
    .chat-list-item {
        padding: 8px 12px;
        margin: 4px 0;
        border-radius: 8px;
        cursor: pointer;
        transition: background-color 0.2s;
    }
    .chat-list-item:hover {
        background-color: rgba(255, 255, 255, 0.1);
    }
    .chat-list-title {
        font-size: 14px;
        font-weight: 500;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .chat-list-time {
        font-size: 11px;
        color: #888;
    }
    .new-chat-btn {
        width: 100%;
        margin-bottom: 16px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.subheader("💬 Chats")
    
    # New Chat Button
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("➕ New Chat", key="new_chat_btn", use_container_width=True):
            start_new_persistent_chat()
            st.rerun()
    with col2:
        if st.button("🔄", key="refresh_chats", help="Refresh chat list"):
            st.session_state.chat_list_cache = _api_list_chats()
            st.rerun()
    
    # Load chat list
    if not st.session_state.chat_list_cache:
        st.session_state.chat_list_cache = _api_list_chats()
    
    chat_list = st.session_state.chat_list_cache
    
    if chat_list:
        for chat in chat_list[:20]:  # Show last 20 chats
            chat_id = chat.get("chat_id", "")
            title = chat.get("title", "New Chat")
            updated = _format_timestamp(chat.get("updated_at", ""))
            
            is_active = chat_id == st.session_state.persistent_chat_id
            
            col_a, col_b = st.columns([5, 1])
            with col_a:
                btn_label = f"{'▶ ' if is_active else ''}{title[:25]}{'...' if len(title) > 25 else ''}"
                if st.button(btn_label, key=f"chat_{chat_id}", use_container_width=True):
                    load_persistent_chat(chat_id)
                    st.rerun()
            with col_b:
                if st.button("🗑️", key=f"del_{chat_id}", help="Delete chat"):
                    delete_persistent_chat(chat_id)
                    st.rerun()
    else:
        st.caption("No previous chats")
    
    st.markdown("---")
    
    # ============ Agent Mode Selection ============
    st.subheader("🤖 Agent Mode")
    
    agent_mode = st.selectbox(
        "Select Agent",
        ["Pixel Copilot", "Finance Assistant", "Healthcare Assistant"],
        key="agent_mode"
    )
    
    # Map to domain names
    domain_map = {
        "Pixel Copilot": "pixel",
        "Finance Assistant": "finance",
        "Healthcare Assistant": "healthcare"
    }
    current_domain = domain_map[agent_mode]
    
    # Reset chat on domain switch
    if "last_domain" not in st.session_state:
        st.session_state.last_domain = current_domain
    elif st.session_state.last_domain != current_domain:
        st.session_state.chat_history = []
        st.session_state.persistent_chat_id = None
        st.session_state.last_domain = current_domain
        st.rerun()
    
    st.markdown("---")
    
    # ============ Original Options Section ============
    st.header("Options")
    
    # Memory toggle (NEW)
    memory_enabled = st.checkbox("💾 Enable Memory", value=st.session_state.memory_enabled, 
                                  help="Save chat history persistently")
    if memory_enabled != st.session_state.memory_enabled:
        st.session_state.memory_enabled = memory_enabled
    
    kb_threshold = st.slider("KB Confidence Threshold (τ)", 0.0, 0.95, 0.45, 0.01)
    research_only = st.checkbox("Research only (skip KB)", value=False)
    rerank = st.checkbox("Enable Re-ranking", value=True)
    web_enabled = st.checkbox("Enable Web Search (fallback)", value=True)
    youtube_enabled = st.checkbox("Enable YouTube Suggestions", value=False)

    embed_choice = st.selectbox("Embeddings backend", [
        "hash (local, no keys)",
        "ollama:nomic-embed-text",
        "ollama:mxbai-embed-large",
    ], index=1)  # Default to ollama:nomic-embed-text to match index
    embed_backend = "hash" if embed_choice.startswith("hash") else embed_choice

    sum_choice = st.selectbox("Summarizer LLM (Ollama)", [
        "none (heuristic)",
        "ollama:llama3.2",
        "ollama:deepseek-r1:1.5b",
    ])
    summarizer_model = "none" if sum_choice.startswith("none") else sum_choice.split("ollama:",1)[1]

    show_graph = st.checkbox("Show agent graph", value=True)

    st.markdown("---")
    st.subheader("Upload to KB")
    up = st.file_uploader("Add files", type=["pdf","md","markdown","txt","csv","json"])
    if up is not None:
        files = {"file": (up.name, up.getvalue())}
        try:
            r = requests.post(f"{API_BASE}/upload", files=files, timeout=120)
            if r.ok and r.json().get("ok"):
                st.success(f"Uploaded: {up.name}")
        except Exception as e:
            st.error(f"Upload error: {e}")

# Main content
if show_graph:
    st.subheader("Agent Graph")
    st.graphviz_chart(graph_dot(), use_container_width=True)

# Display chat messages
for m in st.session_state.chat_history:
    with st.chat_message(m["role"]):
        if m["role"] == "assistant":
            st.markdown(m["content"])
        else:
            st.write(m["content"])

# Chat input
prompt = st.chat_input("Ask a question...")

def _stream_api(message, kb_threshold, research_only, rerank, embed_backend, history_msgs, web_enabled, youtube_enabled, summarizer_model, domain):
    params = {
        "message": message,
        "domain": domain,
        "kb_threshold": kb_threshold,
        "research_only": research_only,
        "rerank": rerank,
        "embed_backend": embed_backend,
        "web_enabled": web_enabled,
        "youtube_enabled": youtube_enabled,
        "summarizer_model": summarizer_model,
        "history": json.dumps(history_msgs)
    }
    with requests.get(f"{API_BASE}/chat_stream", params=params, stream=True, timeout=180) as r:
        r.raise_for_status()
        answer_chunks = []
        youtube_suggestions = []
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                payload = json.loads(line[6:])
                if "delta" in payload:
                    answer_chunks.append(payload["delta"])
                if payload.get("done"):
                    youtube_suggestions = payload.get("youtube_suggestions", [])
                    break
        full_answer = "".join(answer_chunks)
        st.markdown(full_answer)

        # Render YouTube video cards if available
        if youtube_suggestions:
            st.markdown("---")
            st.markdown("🎬 Related YouTube Videos")
            cols = st.columns(3)
            for idx, video in enumerate(youtube_suggestions[:6]):
                with cols[idx % 3]:
                    video_url = video.get("video_url", "")
                    title = video.get("title", "Video")
                    thumbnail = video.get("thumbnail_url", "")

                    yt_ok = video_url.startswith("https://www.youtube.com/watch?v=") or video_url.startswith("https://youtu.be/")
                    thumb_ok = thumbnail.startswith("https://img.youtube.com/vi/")

                    if yt_ok and thumb_ok:
                        safe_title = html.escape(title[:60])
                        safe_url = html.escape(video_url)
                        safe_thumb = html.escape(thumbnail)
                        st.markdown(f"""
                        <div style="background:#1e1e2e;border-radius:8px;overflow:hidden;margin-bottom:12px;">
                            <a href="{safe_url}" target="_blank" rel="noopener noreferrer">
                                <img src="{safe_thumb}" style="width:100%;height:auto;display:block;">
                                <div style="padding:8px;font-size:11px;color:#ccc;">{safe_title}</div>
                            </a>
                        </div>
                        """, unsafe_allow_html=True)
        
        return full_answer

if prompt:
    # Create a new persistent chat if memory is enabled and no chat exists
    if st.session_state.memory_enabled and not st.session_state.persistent_chat_id:
        result = _api_create_chat()
        if result.get("chat_id"):
            st.session_state.persistent_chat_id = result["chat_id"]
            st.session_state.chat_list_cache = _api_list_chats()
    
    context_query = _build_context_prompt(st.session_state.chat_history, prompt)
    
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    
    # Save user message to persistent storage
    save_message_to_persistent("user", prompt)
    
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        try:
            ans = _stream_api(
                message=context_query,
                kb_threshold=kb_threshold,
                research_only=research_only,
                rerank=rerank,
                embed_backend=embed_backend,
                history_msgs=st.session_state.chat_history[-6:],
                web_enabled=web_enabled,
                youtube_enabled=youtube_enabled,
                summarizer_model=summarizer_model,
                domain=st.session_state.get("last_domain", "pixel"),
            )
            st.session_state.chat_history.append({"role": "assistant", "content": ans})
            
            # Save assistant message to persistent storage
            save_message_to_persistent("assistant", ans)
            
            save_current_chat()
            
            # Refresh chat list to show updated title
            if st.session_state.memory_enabled:
                st.session_state.chat_list_cache = _api_list_chats()
        except Exception as e:
            st.error(f"API error: {e}")
