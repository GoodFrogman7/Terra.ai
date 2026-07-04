"""
Context builder for memory injection.
Builds context from chat history and long-term memory to inject into agent state.
This is ADDITIVE ONLY - does not replace or modify existing prompt logic.
"""
import logging
import os
from typing import Dict, Any, List, Optional
from core.memory.store import get_chat_store, get_memory_store

logger = logging.getLogger("memory_context")
logger.setLevel(logging.DEBUG if os.getenv("MEMORY_DEBUG", "").lower() == "true" else logging.INFO)


def build_memory_context(
    chat_id: Optional[str] = None,
    include_long_term: bool = True,
    max_messages: int = 10,
    max_memories: int = 5,
    user_id: str = "local"
) -> Dict[str, Any]:
    """
    Build context from memory to inject into agent state.
    
    Returns:
        Dict with:
        - chat_history: List of messages from current chat
        - long_term_memory: List of relevant long-term memories
        - memory_context_text: Formatted text for context injection
        - injected_memory_ids: List of memory IDs used (for debugging)
    """
    chat_store = get_chat_store()
    memory_store = get_memory_store()
    
    result = {
        "chat_history": [],
        "long_term_memory": [],
        "memory_context_text": "",
        "injected_memory_ids": [],
        "active_chat_id": chat_id,
    }
    
    # Load current chat history
    if chat_id and chat_store.chat_exists(chat_id, user_id=user_id):
        messages = chat_store.get_messages(chat_id, limit=max_messages)
        result["chat_history"] = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
        ]
        logger.debug(f"[MEMORY_CONTEXT] Loaded {len(messages)} messages from chat_id={chat_id}")
    
    # Load long-term memory
    if include_long_term:
        memories = memory_store.get_memories(limit=max_memories, user_id=user_id)
        result["long_term_memory"] = memories
        result["injected_memory_ids"] = [m["memory_id"] for m in memories]
        logger.debug(f"[MEMORY_CONTEXT] Loaded {len(memories)} long-term memories, ids={result['injected_memory_ids']}")
    
    # Build context text for injection
    context_parts = []
    
    if result["long_term_memory"]:
        memory_texts = [f"- {m['content']}" for m in result["long_term_memory"]]
        context_parts.append("User context from previous conversations:\n" + "\n".join(memory_texts))
    
    if context_parts:
        result["memory_context_text"] = "\n\n".join(context_parts)
    
    return result


def inject_memory_into_state(state: Dict[str, Any], chat_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Inject memory context into agent state.
    This is ADDITIVE - only adds new keys, does not modify existing state.
    
    Args:
        state: The current agent state
        chat_id: Optional chat ID to load context from
        
    Returns:
        Modified state with memory context added
    """
    memory_ctx = build_memory_context(chat_id=chat_id)
    
    # Add memory context to state (additive only)
    state["_memory_context"] = memory_ctx.get("memory_context_text", "")
    state["_active_chat_id"] = memory_ctx.get("active_chat_id")
    state["_injected_memory_ids"] = memory_ctx.get("injected_memory_ids", [])
    
    # If existing messages are empty but we have chat history, add it
    if not state.get("messages") and memory_ctx.get("chat_history"):
        state["messages"] = memory_ctx["chat_history"]
    
    logger.debug(
        f"[MEMORY_CONTEXT] Injected memory into state: "
        f"chat_id={memory_ctx.get('active_chat_id')}, "
        f"memory_ids={memory_ctx.get('injected_memory_ids')}"
    )
    
    return state


def extract_title_from_message(content: str, max_length: int = 40) -> str:
    """
    Extract a title from the first user message.
    """
    import re
    
    # Clean up the message
    text = content.strip()
    text = re.sub(r'[?!.]+$', '', text)
    
    # Remove common question prefixes
    patterns = [
        r'^(what|how|why|when|where|who|whose|whom|which)\s+(is|are|was|were|do|does|did|can|could|would|will|should|has|have|had)\s+',
        r'^(what|how|why|when|where|who|whose|whom|which)\s+',
        r'^(can you|could you|do you|does|did you|will you|would you|please)\s+',
        r'^(tell me about|tell me|explain|show me|find|search|look up|give me|get me|i want to know about|i need)\s+',
    ]
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Capitalize first letter of each word
    title = text.title() if text else "New Chat"
    
    # Truncate if too long
    if len(title) > max_length:
        title = title[:max_length - 3] + "..."
    
    return title

