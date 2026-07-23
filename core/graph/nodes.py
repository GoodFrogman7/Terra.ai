from typing import Dict, Any, List, Tuple
import os, json, hashlib, re
import logging
import concurrent.futures

from core.rag.retriever import get_default_kb_threshold, kb_retrieve_with_confidence
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
        "embed": state.get("embed_backend") or os.getenv("EMBED_BACKEND","hash"),
        "rerank": bool(state.get("rerank", False)),
        "kb_t": state.get("KB_THRESHOLD", 0.62),
        "web_enabled": bool(state.get("web_enabled", False)),
        "strict_mode": bool(state.get("strict_mode", True)),
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


_REFERENCE_ONLY_WORDS = {"he", "she", "they", "it", "him", "her", "them", "this", "that"}


def _clean_topic(text: str) -> str:
    text = re.sub(r"\b(?:can|could|would)\s+(?:you|u)\b.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:who|what)\s+is\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:tell me about|explain|show me)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[?!.,]+$", "", text).strip()
    return text


def _extract_video_topic(query: str) -> str:
    """Extract the subject of a video request without treating the request as the subject."""
    text = (query or "").strip()
    about_match = re.search(r"\b(?:about|on|for)\s+(.+)$", text, flags=re.IGNORECASE)
    if about_match:
        return _clean_topic(about_match.group(1))

    embedded_subject = re.match(
        r"^(?:who\s+is|tell\s+me\s+about|explain)\s+(.+?)\s+(?:can|could|would)\s+(?:you|u)\s+.*?(?:youtube|video|vids?)",
        text,
        flags=re.IGNORECASE,
    )
    if embedded_subject:
        return _clean_topic(embedded_subject.group(1))

    stripped = re.sub(
        r"^(?:can\s+(?:you|u)\s+)?(?:please\s+)?(?:suggest|recommend|show|find|give\s+me)\s+(?:some\s+)?(?:youtube\s+)?(?:videos?|vids?)\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    stripped = _clean_topic(stripped)
    return stripped if stripped and not _is_video_request_intent(stripped) else ""


def _topic_from_user_message(content: str) -> str:
    content = (content or "").strip()
    if _is_context_dependent_follow_up(content):
        return ""
    video_topic = _extract_video_topic(content) if _is_video_request_intent(content) else ""
    if video_topic:
        return video_topic

    match = re.match(r"^(?:who\s+is|what\s+is|tell\s+me\s+about|explain)\s+(.+)$", content, flags=re.IGNORECASE)
    candidate = _clean_topic(match.group(1) if match else content)
    words = set(re.findall(r"[A-Za-z]+", candidate.lower()))
    if not candidate or words.issubset(_REFERENCE_ONLY_WORDS):
        return ""
    return candidate if len(candidate) > 2 else ""


def _extract_topic_from_history(messages: List[Dict]) -> str:
    """Find the most recent explicit user subject for follow-up resolution."""
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        topic = _topic_from_user_message(msg.get("content", ""))
        if topic:
            return topic
    return ""


def _is_context_dependent_follow_up(query: str) -> bool:
    q = (query or "").lower()
    return bool(
        re.search(r"\b(?:he|she|they|it|him|her|them|his|hers|their|this|that)\b", q)
        or re.match(r"^(?:and|but|why|how|when|where|what\s+about)\b", q)
    )


def _resolve_follow_up_query(query: str, messages: List[Dict]) -> str:
    """Resolve a short pronoun follow-up without polluting a new request with old intents."""
    if not _is_context_dependent_follow_up(query):
        return query
    topic = _extract_topic_from_history(messages)
    if not topic:
        return query

    q = (query or "").strip()
    if re.match(r"^(?:but\s+)?who\s+is\s+(?:he|she|they|it)\??$", q, flags=re.IGNORECASE):
        return f"Who is {topic}?"
    return f"{q} (about {topic})"


def _resolve_video_query(query: str, messages: List[Dict]) -> str:
    """Resolve the video subject from this request, using history only when it is omitted."""
    topic = _extract_video_topic(query)
    if topic:
        return topic
    return _extract_topic_from_history(messages) or "general explainer"


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


def _conversation_context(messages: List[Dict[str, Any]], max_messages: int = 6) -> str:
    lines = []
    for message in messages[-max_messages:]:
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = re.sub(r"\s+", " ", str(message.get("content", ""))).strip()
        if content:
            lines.append(f"{role.title()}: {content[:700]}")
    return "\n".join(lines)


def _clean_research_response(response: str, max_sentences: int = 3, filter_time_sensitive: bool = True) -> str:
    response = re.sub(r"<think>.*?</think>", "", response or "", flags=re.IGNORECASE | re.DOTALL)
    response = re.sub(r"^\s*(?:answer|terra)\s*:\s*", "", response, flags=re.IGNORECASE)
    response = re.sub(r"\s+", " ", response).strip()
    sentences = re.split(r"(?<=[.!?])\s+", response)
    stable_sentences = sentences
    if filter_time_sensitive:
        stable_sentences = [
            sentence
            for sentence in sentences
            if not re.search(
                r"\b(?:current|currently|today|latest|as of|captains?|ceo|president|prime minister)\b",
                sentence,
                flags=re.IGNORECASE,
            )
        ]
    selected = stable_sentences[:max_sentences]
    return " ".join(sentence for sentence in selected if sentence).strip()


def _research_model_answer(state: Dict[str, Any], question: str, max_sentences: int = 3) -> str:
    """Use the configured local model for conversational Research-mode replies."""
    model = state.get("summarizer_model", "none")
    if not model or model.lower() == "none":
        return ""
    conversation = _conversation_context(state.get("messages", []))
    prompt = f"""You are Terra Research, a capable conversational assistant.
Answer the current request directly and concisely in at most {max_sentences} sentences.
Use the conversation only to resolve references such as he, she, it, or that.
When resolving a reference, repeat the resolved subject's name in the first sentence.
Do not mention prompts, context, knowledge bases, policies, or sources unless the user asks.
Avoid time-sensitive claims such as current roles, prices, or records unless they are verified in supplied sources.
Do not invent certainty when unsure.

Conversation:
{conversation or "(no earlier conversation)"}

Current request: {question}

Answer:"""
    try:
        return _clean_research_response(_ollama_generate(model=model, prompt=prompt, timeout=45) or "", max_sentences=max_sentences)
    except Exception:
        return ""


def _grounded_web_answer(state: Dict[str, Any], sources: List[Dict[str, Any]], max_sentences: int = 3) -> str:
    """Write a research answer from the live source excerpts, never model memory."""
    model = state.get("summarizer_model", "none")
    if not model or model.lower() == "none":
        return ""
    evidence = "\n\n".join(
        f"Source: {item.get('title', 'web')}\nExcerpt: {item.get('content', '')}"
        for item in sources[:4]
    )
    prompt = f"""You are Terra Research. Answer the question in at most {max_sentences} sentences.
Use only the live source excerpts below. Do not use background knowledge, make up details,
or contradict the excerpts. For a time-sensitive claim, state only what the excerpts support.
If the excerpts do not answer the question, say that you cannot verify it from the live sources.
Use the clearest concrete wording in the excerpts; never replace a stated event with vague
placeholders such as "something" or add an unverified explanation of its cause. Answer directly
rather than narrating what the excerpts do not say unless that limitation is necessary.

Question: {state.get('query', '')}

Live source excerpts:
{evidence}

Answer:"""
    try:
        answer = _clean_research_response(
            _ollama_generate(model=model, prompt=prompt, timeout=45) or "",
            max_sentences=max_sentences,
            filter_time_sensitive=False,
        )
        return _clean_vague_event_wording(answer)
    except Exception:
        return ""


def _requires_live_verification(query: str) -> bool:
    """Questions whose answer must not come from a stale model snapshot."""
    return bool(
        re.search(
            r"\b(?:alive|dead|death|died|dies|dying|pass(?:ed)?\s+away|obituary|current|currently|today|latest|breaking|news|price|stock|weather|score|election)\b",
            query or "",
            flags=re.IGNORECASE,
        )
    )


def _live_research_unavailable_payload() -> Dict[str, Any]:
    return {
        "answer": "I couldn't verify that with live web sources, so I won't guess.",
        "citations": [],
        "source": "none",
        "youtube_suggestions": [],
    }


def _clean_vague_event_wording(answer: str) -> str:
    """Keep a source-supported event description from being degraded into filler."""
    answer = re.sub(
        r"(?:when\s+)?the helicopter (?:he|she|they) was (?:in|travelling in) "
        r"collided with something(?:, resulting in (?:his|her|their) death(?: along with [^.]+)?)?",
        "in a helicopter collision",
        answer,
        flags=re.IGNORECASE,
    )
    if "helicopter collision" in answer.lower():
        answer = re.sub(
            r"\s*The exact (?:details|cause) of the collision (?:are|is) not specified in the (?:provided )?(?:excerpts|sources)\.",
            "",
            answer,
            flags=re.IGNORECASE,
        )
    return re.sub(r"\s+", " ", answer).strip()


def _video_response_payload(state: Dict[str, Any]) -> Dict[str, Any] | None:
    """Attach video suggestions to a short answer; video discovery never replaces the answer."""
    video_query = state.get("_video_query", state.get("query", ""))
    videos = _get_youtube_nonblocking(video_query, max_results=6, timeout=5.0)
    if not videos:
        return None

    intro_question = f"Give a concise factual introduction to {video_query} for someone asking for related videos."
    intro = _research_model_answer(state, intro_question, max_sentences=2)
    answer = intro or f"Here are a few YouTube videos about {video_query}."
    if intro:
        answer = f"{intro}\n\nHere are a few relevant YouTube videos."
    return {"answer": answer, "citations": [], "source": "youtube", "youtube_suggestions": videos}

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
    seen_sources = set()
    for item in items[:max_items]:
        content = (item.get("content") or "").strip()
        source_key = (item.get("title", "source"), item.get("url", ""))
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)
        citations.append({
            "title": item.get("title", "source"),
            "url": item.get("url", ""),
            "snippet": content[:200],
            "score": round(float(item.get("score", 0.0)), 3),
        })
    return citations


_EVIDENCE_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could", "do",
    "does", "for", "from", "how", "i", "in", "is", "it", "me", "my", "of",
    "on", "or", "please", "should", "that", "the", "their", "this", "to", "was",
    "what", "when", "where", "which", "who", "why", "with", "would", "you", "your",
}


def _evidence_terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z0-9]+", (text or "").lower())
        if len(token) > 1 and token not in _EVIDENCE_STOP_WORDS
    }


def _source_segments(text: str) -> List[str]:
    """Keep source wording while pairing a Markdown heading with its paragraph."""
    segments: List[str] = []
    heading = ""
    paragraph: List[str] = []
    heading_emitted = False

    def flush() -> None:
        nonlocal paragraph, heading_emitted
        body = " ".join(part.strip() for part in paragraph if part.strip())
        body = re.sub(r"\s+", " ", body).strip()
        if body:
            segments.append(f"{heading}: {body}" if heading else body)
            heading_emitted = True
        elif heading and len(heading) > 180 and not heading_emitted:
            # Chunking can collapse a Markdown heading and its source paragraph
            # onto one line. Preserve that raw evidence rather than dropping it.
            segments.append(heading)
            heading_emitted = True
        paragraph = []

    for line in (text or "").splitlines():
        clean = line.strip()
        if not clean:
            flush()
            continue
        if clean.startswith("#"):
            flush()
            heading = re.sub(r"^#+\s*", "", clean).strip()
            heading_emitted = False
            continue
        paragraph.append(clean)
    flush()
    return segments


def _extractive_evidence(query: str, items: List[Dict[str, Any]], max_segments: int = 2) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Select source excerpts only; this path never rewrites or infers evidence."""
    query_terms = _evidence_terms(query)
    if not query_terms:
        return [], []

    candidates = []
    for item_index, item in enumerate(items):
        content = item.get("content") or item.get("snippet") or ""
        for segment_index, segment in enumerate(_source_segments(content)):
            if len(segment) < 24 or len(segment) > 900:
                continue
            overlap = len(query_terms & _evidence_terms(segment))
            if overlap:
                candidates.append((overlap, float(item.get("score", 0.0)), item_index, segment_index, segment, item))

    candidates.sort(key=lambda candidate: (-candidate[0], -candidate[1], candidate[2], candidate[3]))
    excerpts: List[str] = []
    source_items: List[Dict[str, Any]] = []
    seen_excerpts = set()
    for _, _, _, _, segment, item in candidates:
        normalized = re.sub(r"\s+", " ", segment).strip()
        if normalized in seen_excerpts:
            continue
        excerpts.append(normalized)
        source_items.append(item)
        seen_excerpts.add(normalized)
        if len(excerpts) >= max_segments:
            break
    return excerpts, source_items


def _strict_no_answer_payload() -> Dict[str, Any]:
    return {
        "answer": "I cannot verify that in the approved sources.",
        "citations": [],
        "source": "none",
        "youtube_suggestions": [],
        "_strict_evidence": [],
    }


def intake(state: Dict[str, Any]) -> Dict[str, Any]:
    # NEW: Inject memory context (additive only)
    state = _inject_memory_context(state)
    
    history = state.get("messages", [])
    user_query = (state.get("query") or "").strip()
    q = _resolve_follow_up_query(user_query, history)
    
    # Route media only from the current request. History may supply a missing
    # subject, but it must never make an ordinary follow-up look like a video request.
    is_video_request = _is_video_request_intent(user_query)
    state["_is_video_request"] = is_video_request
    state["user_query"] = user_query
    
    if is_video_request and state.get("youtube_enabled", False) and not state.get("strict_mode", True):
        state["_video_query"] = _resolve_video_query(user_query, history)
    
    state["query"] = q
    requested_threshold = state.get("KB_THRESHOLD")
    kb_base = (
        float(requested_threshold)
        if requested_threshold is not None
        else get_default_kb_threshold(
            domain=state.get("domain", "finance"),
            embed_backend=state.get("embed_backend"),
        )
    )
    state["KB_THRESHOLD"] = _apply_intent_thresholds(q, kb_base)
    return state

def kb_retrieve(state: Dict[str, Any]) -> Dict[str, Any]:
    if state.get("force_research"):
        return {**state, "kb_hits": [], "kb_conf": 0.0}
    domain = state.get("domain", "finance")
    hits, conf = kb_retrieve_with_confidence(
        state["query"],
        rerank=bool(state.get("rerank", False)),
        domain=domain,
        embed_backend=state.get("embed_backend"),
    )
    return {**state, "kb_hits": hits, "kb_conf": conf}

def answer_from_kb(state: Dict[str, Any]) -> Dict[str, Any]:
    cache_k = _cache_key(state)
    if _CACHE_ENABLED and cache_k in _ANSWER_CACHE:
        return {**state, **_ANSWER_CACHE[cache_k]}
    
    # Check if this is a video-first request
    is_video_request = state.get("_is_video_request", False)
    # Media requests receive a brief answer and then video suggestions.
    # Strict policy mode never takes this branch.
    if is_video_request and state.get("youtube_enabled", False) and not state.get("strict_mode", True):
        payload = _video_response_payload(state)
        if payload:
            if _CACHE_ENABLED:
                _ANSWER_CACHE[cache_k] = payload
            return {**state, **payload}

    hits: List[Dict[str, Any]] = state.get("kb_hits", [])
    top = hits[:3]
    model = state.get("summarizer_model", "none")

    if state.get("strict_mode", True):
        excerpts, evidence_sources = _extractive_evidence(state["query"], top)
        if not excerpts:
            return {**state, **_strict_no_answer_payload()}
        payload = {
            "answer": f"**(KB)** {' '.join(excerpts)}",
            "citations": _build_citations(evidence_sources),
            "source": "kb",
            "youtube_suggestions": [],
            "_strict_evidence": excerpts,
        }
        if _CACHE_ENABLED:
            _ANSWER_CACHE[cache_k] = payload
        return {**state, **payload}

    # Exploratory mode can synthesize retrieved context. Pilot mode never takes this path.
    answer = summarize(state["query"], top, mode="kb", model=model)
    answer = f"**(KB)** {answer}"

    payload = {"answer": answer, "citations": _build_citations(top), "source": "kb", "youtube_suggestions": []}
    if _CACHE_ENABLED:
        _ANSWER_CACHE[cache_k] = payload
    return {**state, **payload}

def kb_no_answer(state: Dict[str, Any]) -> Dict[str, Any]:
    model = state.get("summarizer_model", "none")
    
    # Check if this is a video-first request
    is_video_request = state.get("_is_video_request", False)
    # In Research mode, videos are an addition to the answer, not a replacement for it.
    if is_video_request and state.get("youtube_enabled", False) and not state.get("strict_mode", True):
        payload = _video_response_payload(state)
        if payload:
            return {**state, **payload}

    if state.get("strict_mode", True):
        return {**state, **_strict_no_answer_payload()}

    # A live-research request or a freshness-sensitive question must never silently
    # fall back to stale model memory after web evidence is absent.
    if state.get("web_enabled", False) or _requires_live_verification(state.get("query", "")):
        return {**state, **_live_research_unavailable_payload()}

    fallback = _research_model_answer(state, state["query"])
    if fallback:
        payload = {"answer": fallback, "citations": [], "source": "general_knowledge", "youtube_suggestions": []}
        return {**state, **payload}

    msg = "I don't have enough verified information to answer that accurately."
    payload = {"answer": msg, "citations": [], "source": "none", "youtube_suggestions": []}
    return {**state, **payload}

def research_plan(state: Dict[str, Any]) -> Dict[str, Any]:
    return {**state, "plan": [state["query"]]}

def web_research(state: Dict[str, Any]) -> Dict[str, Any]:
    res = web_search_bundle(state["query"])
    return {
        **state,
        "web_snippets": res.get("snippets", []),
        "web_conf": res.get("confidence", 0.0),
        "web_search_provider": res.get("provider", "none"),
        "web_search_error": res.get("error", ""),
    }

def synthesize_research(state: Dict[str, Any]) -> Dict[str, Any]:
    cache_k = _cache_key(state)
    if _CACHE_ENABLED and cache_k in _ANSWER_CACHE:
        return {**state, **_ANSWER_CACHE[cache_k]}
    
    # Check if this is a video-first request - YouTube takes priority, suppress web
    is_video_request = state.get("_is_video_request", False)
    if is_video_request and state.get("youtube_enabled", False) and not state.get("strict_mode", True):
        payload = _video_response_payload(state)
        if payload:
            if _CACHE_ENABLED:
                _ANSWER_CACHE[cache_k] = payload
            return {**state, **payload}

    snips: List[Dict[str, Any]] = state.get("web_snippets", [])
    top = [{"title": s.get("title","web"), "url": s.get("url",""), "content": s.get("snippet",""), "score": state.get("web_conf",0.0)} for s in snips[:4]]
    model = state.get("summarizer_model", "none")

    if not top:
        # No approved evidence means no web answer or misleading Web label.
        return kb_no_answer({**state, "web_snippets": []})

    if state.get("strict_mode", True):
        excerpts, evidence_sources = _extractive_evidence(state["query"], top)
        if not excerpts:
            return {**state, **_strict_no_answer_payload()}
        payload = {
            "answer": f"**(Web)** {' '.join(excerpts)}",
            "citations": _build_citations(evidence_sources),
            "source": "web",
            "youtube_suggestions": [],
            "_strict_evidence": excerpts,
        }
        if _CACHE_ENABLED:
            _ANSWER_CACHE[cache_k] = payload
        return {**state, **payload}

    # The answer may be conversational, but it is constrained to the retrieved live evidence.
    answer = _grounded_web_answer(state, top)
    if not answer:
        excerpts, _ = _extractive_evidence(state["query"], top, max_segments=1)
        answer = excerpts[0] if excerpts else "I couldn't verify that from the live sources."

    payload = {
        "answer": f"**(Web)** {answer}",
        "citations": _build_citations(top),
        "source": "web",
        "youtube_suggestions": [],
    }
    if _CACHE_ENABLED:
        _ANSWER_CACHE[cache_k] = payload
    return {**state, **payload}

def policy_gate(state: Dict[str, Any]) -> Dict[str, Any]:
    # Grounded labels are a trust contract: never emit KB/Web without sources.
    if state.get("source") in {"kb", "web"} and not state.get("citations"):
        state = {
            **state,
            "answer": "I don't have enough verified information to answer that accurately.",
            "citations": [],
            "source": "none",
        }
    strict_evidence_rejected = (
        state.get("strict_mode", True)
        and state.get("source") in {"kb", "web"}
        and not state.get("_strict_evidence")
    )
    if strict_evidence_rejected:
        state = {**state, **_strict_no_answer_payload()}
    flags = list(requires_human_review(state))
    if strict_evidence_rejected:
        flags.append("strict_evidence_rejected")
    return {**state, "policy_flags": flags}
