from typing import Dict, Any, List
import os, json, hashlib
import logging
import concurrent.futures

from core.rag.retriever import kb_retrieve_with_confidence
from core.tools.web_search import web_search_bundle
from core.tools.youtube_search import get_youtube_suggestions_structured
from core.safety.policies import requires_human_review
from core.llm.summarizer import summarize, _ollama_generate

# Memory context injection (additive only)
_memory_logger = logging.getLogger("memory_inject")
_memory_logger.setLevel(logging.DEBUG if os.getenv("MEMORY_DEBUG", "").lower() == "true" else logging.INFO)

# Disable cache to always get fresh LLM responses
_ANSWER_CACHE: dict[str, dict] = {}
_CACHE_ENABLED = False  # Set to True to enable caching

def _cache_key(state: Dict[str, Any]) -> str:
    sel = {
        "q": state.get("query",""),
        "hist": state.get("messages", [])[-4:],
        "embed": os.getenv("EMBED_BACKEND","hash"),
        "rerank": bool(state.get("rerank", False)),
        "kb_t": state.get("KB_THRESHOLD", 0.62),
        "web_enabled": bool(state.get("web_enabled", True)),
        "sum_model": state.get("summarizer_model", "none"),
    }
    return hashlib.sha256(json.dumps(sel, sort_keys=True).encode("utf-8")).hexdigest()

def _apply_intent_thresholds(query: str, base: float) -> float:
    q = (query or "").lower()
    if "factory reset" in q or "wipe" in q:
        return max(base, 0.75)
    if "how to" in q or "enable" in q or "turn on" in q:
        return min(base, 0.55)
    return base


def _is_video_request_intent(query: str) -> bool:
    """Check if user is asking for video suggestions/recommendations."""
    q = (query or "").lower()
    video_patterns = [
        "suggest video", "video suggest", "suggest some video", "give video",
        "show video", "recommend video", "video recommend", "any video",
        "some video", "find video", "search video", "youtube", "watch video",
        "video for", "videos about", "video on", "show me video", "give me video",
        "want video", "need video", "looking for video", "video please",
        "suggest a video", "recommend a video", "show a video",
    ]
    return any(p in q for p in video_patterns)


def _extract_topic_from_history(messages: List[Dict]) -> str:
    """Extract the most recent topic from conversation history."""
    import re
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            # Skip video request messages themselves
            if _is_video_request_intent(content):
                continue
            # Extract meaningful topic
            content = re.sub(r'^(how to|what is|tell me about|explain|show me)\s+', '', content, flags=re.IGNORECASE)
            content = re.sub(r'[?!.,]+$', '', content).strip()
            if content and len(content) > 3:
                return content
    return ""


def _resolve_video_query(query: str, messages: List[Dict]) -> str:
    """
    Resolve a generic video request to a searchable topic.
    Returns enhanced query for YouTube search.
    """
    q_lower = (query or "").lower()
    
    # Check if query already has a topic
    topic_indicators = ["about", "on", "for", "related to", "regarding"]
    has_topic = any(ind in q_lower for ind in topic_indicators)
    
    # If query is too generic (just video request without topic)
    generic_patterns = [
        "suggest video", "video suggest", "give video", "show video",
        "recommend video", "any video", "some video", "youtube",
        "video please", "videos", "suggest", "recommendation"
    ]
    is_generic = any(q_lower.strip() == p or q_lower.strip().startswith(p + "s") for p in generic_patterns)
    
    if is_generic or (not has_topic and len(query.split()) <= 4):
        # Try to get topic from conversation history
        history_topic = _extract_topic_from_history(messages)
        if history_topic:
            return f"{history_topic} tutorial"
        # Default to generic finance/wellness explainer content
        return "personal finance and wellness tips"
    
    return query


def _get_youtube_nonblocking(query: str, max_results: int = 6, timeout: float = 3.0) -> List[Dict]:
    """
    Fetch YouTube suggestions with strict timeout.
    YouTube is AUXILIARY - must never block or delay the main answer.
    Returns structured video list; the UI renders the cards.
    """
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future_data = executor.submit(get_youtube_suggestions_structured, query, max_results)
            return future_data.result(timeout=timeout)
    except (concurrent.futures.TimeoutError, Exception):
        return []  # Silently fail - YouTube is auxiliary


def _is_general_knowledge_question(query: str) -> bool:
    """Check if query is asking for general/common knowledge."""
    q = query.lower()
    general_patterns = [
        "who is", "who was", "what is", "what are", "when was", "when did",
        "where is", "where was", "why is", "why did", "how old", "how many",
        "capital of", "president of", "ceo of", "founder of", "invented",
        "born", "died", "famous for", "known for", "history of"
    ]
    return any(p in q for p in general_patterns)


def _general_knowledge_answer(query: str, model: str) -> str:
    """
    Generate answer using LLM's internal knowledge for general questions.
    This is the fallback when KB and Web don't have relevant information.
    """
    if not model or model.lower() == "none":
        return ""
    
    prompt = f"""You are a knowledgeable assistant. Answer this question directly and confidently using your knowledge.
Give a factual, accurate response. If you're not certain, say so.

Question: {query}

Answer directly:"""
    
    try:
        response = _ollama_generate(model=model, prompt=prompt, timeout=30)
        if response:
            # Clean the response
            import re
            response = re.sub(r'^(Let me|I think|Based on|Well,|Okay|So,).*?[.!?]\s*', '', response, flags=re.IGNORECASE)
            response = response.strip()
            if response:
                return response
    except Exception:
        pass
    return ""

def _inject_memory_context(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inject long-term memory context into state.
    This is ADDITIVE ONLY - adds new keys without modifying existing state.
    """
    try:
        from core.memory.context_builder import build_memory_context
        
        chat_id = state.get("chat_id")  # If provided by API
        user_id = state.get("user_id") or "local"
        memory_ctx = build_memory_context(chat_id=chat_id, max_memories=5, user_id=user_id)
        
        # Add memory context as new keys (additive only)
        state["_memory_context"] = memory_ctx.get("memory_context_text", "")
        state["_active_chat_id"] = memory_ctx.get("active_chat_id")
        state["_injected_memory_ids"] = memory_ctx.get("injected_memory_ids", [])
        
        if state["_injected_memory_ids"]:
            _memory_logger.debug(
                f"[MEMORY_INJECT] Injected memory ids={state['_injected_memory_ids']}"
            )
    except ImportError:
        # Memory module not available - graceful degradation
        pass
    except Exception as e:
        _memory_logger.warning(f"[MEMORY_INJECT] Failed to inject memory: {e}")
    
    return state


def _build_citations(items: List[Dict[str, Any]], max_items: int = 4) -> List[Dict[str, Any]]:
    """Build citation objects (title/url/snippet/score) from KB hits or web snippets."""
    citations = []
    for item in items[:max_items]:
        content = (item.get("content") or "").strip()
        citations.append({
            "title": item.get("title", "source"),
            "url": item.get("url", ""),
            "snippet": content[:200],
            "score": round(float(item.get("score", 0.0)), 3),
        })
    return citations


def intake(state: Dict[str, Any]) -> Dict[str, Any]:
    # NEW: Inject memory context (additive only)
    state = _inject_memory_context(state)
    
    history = state.get("messages", [])
    q = (state.get("query") or "").strip()
    if history:
        last_user = [m["content"] for m in history if m.get("role")=="user"][-1:] or [""]
        q = (last_user[0] + " " + q).strip()
    
    # Detect video request intent and resolve topic
    is_video_request = _is_video_request_intent(q)
    state["_is_video_request"] = is_video_request
    
    if is_video_request and state.get("youtube_enabled", False):
        # Resolve generic video requests to a searchable topic
        state["_video_query"] = _resolve_video_query(q, history)
    
    state["query"] = q
    kb_base = float(state.get("KB_THRESHOLD", 0.62))
    state["KB_THRESHOLD"] = _apply_intent_thresholds(q, kb_base)
    return state

def kb_retrieve(state: Dict[str, Any]) -> Dict[str, Any]:
    if state.get("force_research"):
        return {**state, "kb_hits": [], "kb_conf": 0.0}
    domain = state.get("domain", "finance")
    hits, conf = kb_retrieve_with_confidence(state["query"], rerank=bool(state.get("rerank", False)), domain=domain)
    return {**state, "kb_hits": hits, "kb_conf": conf}

def answer_from_kb(state: Dict[str, Any]) -> Dict[str, Any]:
    cache_k = _cache_key(state)
    if _CACHE_ENABLED and cache_k in _ANSWER_CACHE:
        return {**state, **_ANSWER_CACHE[cache_k]}
    
    # Check if this is a video-first request
    is_video_request = state.get("_is_video_request", False)
    video_query = state.get("_video_query", state["query"])
    
    # Handle video-first requests: YouTube takes priority, no web fallback
    if is_video_request and state.get("youtube_enabled", False):
        yt_data = _get_youtube_nonblocking(video_query, max_results=6, timeout=5.0)
        if yt_data:
            answer = "Here are some video suggestions for you:"
            payload = {"answer": answer, "citations": [], "source": "youtube", "youtube_suggestions": yt_data}
            if _CACHE_ENABLED:
                _ANSWER_CACHE[cache_k] = payload
            return {**state, **payload}

    hits: List[Dict[str, Any]] = state.get("kb_hits", [])
    top = hits[:3]
    model = state.get("summarizer_model", "none")

    # STEP 1: Generate the main answer FIRST (this is the priority)
    answer = summarize(state["query"], top, mode="kb", model=model)
    answer = f"**(KB)** {answer}"

    # STEP 2: Fetch YouTube AFTER answer is ready (non-blocking, auxiliary only)
    youtube_suggestions = []
    if state.get("youtube_enabled", False):
        youtube_suggestions = _get_youtube_nonblocking(state["query"], max_results=6, timeout=3.0)

    payload = {"answer": answer, "citations": _build_citations(top), "source": "kb", "youtube_suggestions": youtube_suggestions}
    if _CACHE_ENABLED:
        _ANSWER_CACHE[cache_k] = payload
    return {**state, **payload}

def kb_no_answer(state: Dict[str, Any]) -> Dict[str, Any]:
    model = state.get("summarizer_model", "none")
    
    # Check if this is a video-first request
    is_video_request = state.get("_is_video_request", False)
    video_query = state.get("_video_query", state["query"])
    
    # Handle video-first requests: YouTube takes priority
    if is_video_request and state.get("youtube_enabled", False):
        yt_data = _get_youtube_nonblocking(video_query, max_results=6, timeout=5.0)
        if yt_data:
            answer = "Here are some video suggestions for you:"
            payload = {"answer": answer, "citations": [], "source": "youtube", "youtube_suggestions": yt_data}
            return {**state, **payload}

    # Try general knowledge fallback for common questions
    if _is_general_knowledge_question(state["query"]):
        fallback = _general_knowledge_answer(state["query"], model)
        if fallback:
            msg = f"**(Model)** {fallback}\n\n**Source: Model Knowledge**"
            payload = {"answer": msg, "citations": [], "source": "general_knowledge", "youtube_suggestions": []}
            return {**state, **payload}

    msg = "I don't have enough verified information to answer that accurately."
    payload = {"answer": msg, "citations": [], "source": "none", "youtube_suggestions": []}
    return {**state, **payload}

def research_plan(state: Dict[str, Any]) -> Dict[str, Any]:
    return {**state, "plan": [state["query"]]}

def web_research(state: Dict[str, Any]) -> Dict[str, Any]:
    res = web_search_bundle(state["query"])
    return {**state, "web_snippets": res.get("snippets", []), "web_conf": res.get("confidence", 0.0)}

def synthesize_research(state: Dict[str, Any]) -> Dict[str, Any]:
    cache_k = _cache_key(state)
    if _CACHE_ENABLED and cache_k in _ANSWER_CACHE:
        return {**state, **_ANSWER_CACHE[cache_k]}
    
    # Check if this is a video-first request - YouTube takes priority, suppress web
    is_video_request = state.get("_is_video_request", False)
    video_query = state.get("_video_query", state["query"])
    
    if is_video_request and state.get("youtube_enabled", False):
        yt_data = _get_youtube_nonblocking(video_query, max_results=6, timeout=5.0)
        if yt_data:
            answer = "Here are some video suggestions for you:"
            payload = {"answer": answer, "citations": [], "source": "youtube", "youtube_suggestions": yt_data}
            if _CACHE_ENABLED:
                _ANSWER_CACHE[cache_k] = payload
            return {**state, **payload}

    snips: List[Dict[str, Any]] = state.get("web_snippets", [])
    top = [{"title": s.get("title","web"), "url": s.get("url",""), "content": s.get("snippet",""), "score": state.get("web_conf",0.0)} for s in snips[:4]]
    model = state.get("summarizer_model", "none")

    # STEP 1: Generate the main answer FIRST (this is the priority)
    answer = summarize(state["query"], top, mode="web", model=model)

    # STEP 2: If web search failed but this is a general knowledge question, use LLM fallback
    citations: List[Dict[str, Any]] = []
    source = "web"
    if "I don't have enough" in answer and _is_general_knowledge_question(state["query"]):
        fallback = _general_knowledge_answer(state["query"], model)
        if fallback:
            answer = f"**(Model)** {fallback}\n\n**Source: Model Knowledge**"
            source = "general_knowledge"
        else:
            answer = f"**(Web)** {answer}"
    else:
        answer = f"**(Web)** {answer}"
        citations = _build_citations(top)

    # STEP 3: Fetch YouTube AFTER answer is ready (non-blocking, auxiliary only)
    youtube_suggestions = []
    if state.get("youtube_enabled", False):
        youtube_suggestions = _get_youtube_nonblocking(state["query"], max_results=6, timeout=3.0)

    payload = {"answer": answer, "citations": citations, "source": source, "youtube_suggestions": youtube_suggestions}
    if _CACHE_ENABLED:
        _ANSWER_CACHE[cache_k] = payload
    return {**state, **payload}

def policy_gate(state: Dict[str, Any]) -> Dict[str, Any]:
    flags = requires_human_review(state)
    return {**state, "policy_flags": flags}
