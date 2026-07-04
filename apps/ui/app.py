import sys, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
import os, requests, json, re, html
from datetime import datetime
import streamlit as st
from core.graph.graph import graph_dot

API_BASE = os.getenv("COPILOT_API_BASE", "http://127.0.0.1:8000")


# ============ Auth Helpers ============

def _auth_headers() -> dict:
    """Bearer-token header for API calls (empty in local mode)."""
    token = st.session_state.get("access_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


@st.cache_data(ttl=300)
def _api_auth_status() -> bool:
    """Whether this deployment requires login."""
    try:
        r = requests.get(f"{API_BASE}/auth/status", timeout=10)
        if r.ok:
            return bool(r.json().get("auth_enabled"))
    except Exception:
        pass
    return False


def _api_login(email: str, password: str) -> dict:
    r = requests.post(f"{API_BASE}/auth/login", json={"email": email, "password": password}, timeout=20)
    if r.ok:
        return r.json()
    detail = r.json().get("detail", "Login failed") if r.content else "Login failed"
    raise RuntimeError(detail)


def _api_signup(email: str, password: str) -> dict:
    r = requests.post(f"{API_BASE}/auth/signup", json={"email": email, "password": password}, timeout=20)
    if r.ok:
        return r.json()
    detail = r.json().get("detail", "Signup failed") if r.content else "Signup failed"
    raise RuntimeError(detail)


# ============ Memory/Chat API Helpers ============

def _api_create_chat(title: str = "New Chat") -> dict:
    """Create a new chat via API."""
    try:
        r = requests.post(f"{API_BASE}/memory/chats", json={"title": title}, headers=_auth_headers(), timeout=10)
        if r.ok:
            return r.json()
    except Exception as e:
        st.error(f"Failed to create chat: {e}")
    return {}


def _api_list_chats(limit: int = 50) -> list:
    """List all chats from API."""
    try:
        r = requests.get(f"{API_BASE}/memory/chats", params={"limit": limit}, headers=_auth_headers(), timeout=10)
        if r.ok:
            return r.json().get("chats", [])
    except Exception:
        pass
    return []


def _api_get_chat(chat_id: str) -> dict:
    """Get a chat by ID from API."""
    try:
        r = requests.get(f"{API_BASE}/memory/chats/{chat_id}", headers=_auth_headers(), timeout=10)
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
        r = requests.post(f"{API_BASE}/memory/chats/{chat_id}/messages", json=payload, headers=_auth_headers(), timeout=10)
        return r.ok
    except Exception:
        return False


def _api_delete_chat(chat_id: str):
    """Delete a chat."""
    try:
        r = requests.delete(f"{API_BASE}/memory/chats/{chat_id}", headers=_auth_headers(), timeout=10)
        return r.ok
    except Exception:
        return False


@st.cache_data(ttl=300)
def _api_get_config() -> dict:
    """Fetch domains/models/backends from the API (single source of truth)."""
    try:
        r = requests.get(f"{API_BASE}/config", timeout=10)
        if r.ok:
            return r.json()
    except Exception:
        pass
    # Fallback if API is unreachable at first render
    return {
        "domains": {
            "finance": {"name": "Finance Assistant", "description": ""},
            "healthcare": {"name": "Healthcare Assistant", "description": ""},
        },
        "summarizer_models": ["none", "llama3.2"],
        "embed_backends": ["hash", "ollama:nomic-embed-text"],
    }


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

st.set_page_config(page_title="Terra.ai", layout="wide")

# ============ Login Gate ============
if _api_auth_status() and not st.session_state.get("access_token"):
    st.title("Terra.ai")
    st.caption("Grounded, citation-backed AI support for regulated industries.")
    login_tab, signup_tab = st.tabs(["Log in", "Sign up"])
    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log in", use_container_width=True):
                try:
                    result = _api_login(email, password)
                    token = result.get("access_token")
                    if token:
                        st.session_state.access_token = token
                        st.session_state.user_email = result.get("user", {}).get("email", email)
                        st.rerun()
                    st.error("Unexpected response from auth server.")
                except Exception as e:
                    st.error(str(e))
    with signup_tab:
        with st.form("signup_form"):
            email_s = st.text_input("Email", key="signup_email")
            password_s = st.text_input("Password (min 6 chars)", type="password", key="signup_password")
            if st.form_submit_button("Create account", use_container_width=True):
                try:
                    result = _api_signup(email_s, password_s)
                    token = (result.get("session") or {}).get("access_token") or result.get("access_token")
                    if token:
                        st.session_state.access_token = token
                        st.session_state.user_email = email_s
                        st.rerun()
                    st.success("Account created. Check your email to confirm, then log in.")
                except Exception as e:
                    st.error(str(e))
    st.stop()

# Load config from API (domains, models, backends) — single source of truth
_config = _api_get_config()
_domains = _config.get("domains", {})

# Initialize domain state
_default_domain = next(iter(_domains), "finance")
if "last_domain" not in st.session_state:
    st.session_state.last_domain = _default_domain

# Dynamic title based on agent mode
current_domain = st.session_state.get("last_domain", _default_domain)
_domain_display = _domains.get(current_domain, {}).get("name", current_domain.title())
st.title(f"Terra.ai — {_domain_display} (KB-first → Web fallback)")


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
    
    if st.session_state.get("access_token"):
        st.caption(f"Signed in as {st.session_state.get('user_email', 'user')}")
        if st.button("Log out", use_container_width=True):
            st.session_state.pop("access_token", None)
            st.session_state.pop("user_email", None)
            st.session_state.chat_history = []
            st.session_state.persistent_chat_id = None
            st.session_state.chat_list_cache = []
            st.rerun()
        st.markdown("---")

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
        [v.get("name", k) for k, v in _domains.items()],
        key="agent_mode"
    )

    # Map display names back to domain keys (from API config)
    domain_map = {v.get("name", k): k for k, v in _domains.items()}
    current_domain = domain_map[agent_mode]

    # Preserve chat history per domain on switch (no destructive wipe)
    if "domain_chats" not in st.session_state:
        st.session_state.domain_chats = {}
    if "last_domain" not in st.session_state:
        st.session_state.last_domain = current_domain
    elif st.session_state.last_domain != current_domain:
        # Stash the outgoing domain's conversation, restore the incoming one
        st.session_state.domain_chats[st.session_state.last_domain] = {
            "history": st.session_state.chat_history,
            "chat_id": st.session_state.persistent_chat_id,
        }
        restored = st.session_state.domain_chats.get(current_domain, {})
        st.session_state.chat_history = restored.get("history", [])
        st.session_state.persistent_chat_id = restored.get("chat_id")
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

    _embed_options = _config.get("embed_backends", ["hash"])
    _embed_default = _embed_options.index("ollama:nomic-embed-text") if "ollama:nomic-embed-text" in _embed_options else 0
    embed_backend = st.selectbox(
        "Embeddings backend", _embed_options, index=_embed_default,
        help='"hash" is local with no dependencies; ollama:* backends need Ollama running',
    )

    _sum_options = _config.get("summarizer_models", ["none"])
    _sum_default = _sum_options.index("none") if "none" in _sum_options else 0
    summarizer_model = st.selectbox(
        "Summarizer LLM (Ollama)", _sum_options, index=_sum_default,
        help='"none" uses a fast deterministic heuristic; other options need the model pulled in Ollama',
    )

    show_graph = st.checkbox("Show agent graph", value=True)

    st.markdown("---")
    st.subheader("Upload to KB")
    up = st.file_uploader("Add files", type=["pdf","md","markdown","txt","csv","json"])
    if up is not None:
        files = {"file": (up.name, up.getvalue())}
        try:
            r = requests.post(f"{API_BASE}/upload", files=files, headers=_auth_headers(), timeout=120)
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
    placeholder = st.empty()
    placeholder.markdown("_Thinking…_")
    with requests.get(f"{API_BASE}/chat_stream", params=params, headers=_auth_headers(), stream=True, timeout=180) as r:
        r.raise_for_status()
        answer_chunks = []
        youtube_suggestions = []
        citations = []
        source = "unknown"
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                payload = json.loads(line[6:])
                if "delta" in payload:
                    answer_chunks.append(payload["delta"])
                    # Incremental render with a typing cursor
                    placeholder.markdown("".join(answer_chunks) + " ▌")
                if payload.get("done"):
                    youtube_suggestions = payload.get("youtube_suggestions", [])
                    citations = payload.get("citations", [])
                    source = payload.get("source", "unknown")
                    break
        full_answer = "".join(answer_chunks)
        placeholder.markdown(full_answer)

        # Trust indicator: flag answers that aren't grounded in KB/web sources
        if source in ("general_knowledge", "none"):
            st.caption("⚠️ Not grounded in a verified source — model general knowledge only.")

        # Render "Sources" block for grounded (KB/web) answers
        if citations:
            with st.expander(f"📚 Sources ({len(citations)})"):
                for c in citations:
                    title = c.get("title", "source")
                    url = c.get("url", "")
                    snippet = c.get("snippet", "")
                    score = c.get("score", 0.0)
                    if url:
                        st.markdown(f"**[{title}]({url})** · relevance {score:.2f}")
                    else:
                        st.markdown(f"**{title}** · relevance {score:.2f}")
                    if snippet:
                        st.caption(snippet)

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

                    yt_ok = video_url.startswith(("https://www.youtube.com/watch?v=", "https://youtube.com/watch?v=", "https://youtu.be/"))
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
                domain=st.session_state.get("last_domain", "finance"),
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
