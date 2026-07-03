import os, requests, re
from typing import List, Dict, Optional


# ------------------------------------------------------------
# TEXT CLEANING UTILITIES
# ------------------------------------------------------------
def _clean(text: str) -> str:
    """Remove broken spacing, weird formatting, empty lines."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _strip_urls(text: str) -> str:
    """Remove all URLs from text."""
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"www\.\S+", "", text)
    text = re.sub(r"\[.*?\]", "", text)  # Remove markdown links
    return _clean(text)


def _extract_key_info(chunks: List[Dict]) -> str:
    """Extract clean, meaningful text from chunks without URLs or metadata."""
    texts = []
    for ch in chunks[:3]:
        content = ch.get("content", "") or ch.get("snippet", "")
        clean_content = _strip_urls(content)[:400]
        if clean_content:
            texts.append(clean_content)
    return " ".join(texts)


# ------------------------------------------------------------
# OLLAMA LLM CALL
# ------------------------------------------------------------
def _get_ollama_host() -> str:
    """Get OLLAMA_HOST dynamically (not cached at module load)."""
    host = os.getenv("OLLAMA_HOST", "").strip()
    if not host:
        # Default to localhost if not set
        host = "http://localhost:11434"
    return host


def _ollama_generate(model: str, prompt: str, timeout: int = 60) -> Optional[str]:
    """Call Ollama API to generate response."""
    host = _get_ollama_host()
    if not model:
        return None
    
    try:
        url = f"{host}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        response = data.get("response", "")
        if response:
            return response.strip()
        return None
    except requests.exceptions.Timeout:
        print(f"[SUMMARIZER] Ollama timeout after {timeout}s")
        return None
    except requests.exceptions.ConnectionError:
        print(f"[SUMMARIZER] Cannot connect to Ollama at {host}")
        return None
    except Exception as e:
        print(f"[SUMMARIZER] Ollama error: {e}")
        return None


# ------------------------------------------------------------
# CONVERSATIONAL FALLBACK (when LLM unavailable)
# ------------------------------------------------------------
def _heuristic_summarize(query: str, chunks: List[Dict]) -> str:
    """
    Clean, conversational fallback answer without raw evidence or citations.
    Produces chatbot-like responses without using an LLM.
    """
    q_lower = (query or "").lower()
    q_tokens = set(re.findall(r"[a-z0-9]+", q_lower))
    
    # Collect relevant sentences
    all_sentences = []
    for ch in chunks:
        text = _strip_urls(ch.get("content", "") or ch.get("snippet", ""))
        # Remove markdown headers and formatting
        text = re.sub(r'#+\s*', '', text)
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Remove bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)  # Remove italic
        text = re.sub(r'---+', '', text)  # Remove horizontal rules
        text = re.sub(r'-\s+', '', text)  # Remove list markers
        
        # Split into sentences
        parts = re.split(r'(?<=[.!?])\s+', text)
        for p in parts:
            p = p.strip()
            # Skip headers, short fragments, and Q&A format
            if len(p) < 25 or len(p) > 200:
                continue
            if p.startswith('#') or p.startswith('Q:') or p.startswith('**'):
                continue
            # Score by keyword overlap
            p_tokens = set(re.findall(r"[a-z0-9]+", p.lower()))
            overlap = len(q_tokens & p_tokens)
            if overlap >= 2:
                all_sentences.append((overlap, p))
    
    # Sort by relevance and take top 2
    all_sentences.sort(key=lambda x: x[0], reverse=True)
    best = [s[1] for s in all_sentences[:2]]
    
    if not best:
        return "I don't have enough verified information to answer that accurately."
    
    # Build clean response
    answer = ' '.join(best)
    # Clean up any remaining artifacts
    answer = re.sub(r'\s+', ' ', answer)
    answer = re.sub(r'^\d+\)\s*', '', answer)  # Remove numbered list starts
    
    if not answer.endswith('.'):
        answer += '.'
    
    return answer


# ------------------------------------------------------------
# PIXEL COPILOT SYSTEM PROMPT
# ------------------------------------------------------------
PIXEL_COPILOT_SYSTEM = """You are a knowledgeable assistant. Answer questions directly and confidently.

CRITICAL RULES:
1. Give the FINAL ANSWER only. NO thinking, planning, or reasoning out loud.
2. NEVER say "Let me", "I think", "Based on", "From the context", "The user asked".
3. Be direct and concise (1-3 sentences for simple questions, more for complex topics).
4. Use bullet points for steps/lists.
5. For general knowledge (celebrities, history, science, etc.): Answer confidently using your knowledge, supplemented by context.
6. For product-specific questions: Use the provided context.
7. If context contradicts known facts, prefer verified facts.
8. NO meta-commentary about how you found the answer.

CONTEXT SOURCE: {mode}
"""


# ------------------------------------------------------------
# MAIN SUMMARIZE FUNCTION
# ------------------------------------------------------------
def summarize(query: str, chunks: List[Dict], mode: str = "kb", model: Optional[str] = None) -> str:
    """
    Generate a clean, conversational chatbot-style response.
    The LLM rewrites retrieved content into natural language.
    """
    # Extract clean context (strip all URLs and metadata)
    context = _extract_key_info(chunks)
    
    # Determine source label
    source_label = "KB" if mode == "kb" else "Web"
    
    # If no context, return a clean failure message
    if not context or len(context.strip()) < 20:
        if mode == "web":
            return "I don't have enough verified information to answer that accurately."
        return "I don't have specific information about that in my knowledge base."
    
    # Always try to use LLM if model is specified
    if model and model.lower() != "none":
        # Extract the core question without context prefixes
        clean_query = re.sub(r'^Context:.*?Current question:\s*', '', query, flags=re.IGNORECASE)
        
        system_prompt = PIXEL_COPILOT_SYSTEM.format(mode=source_label)
        
        prompt = f"""{system_prompt}

Question: {clean_query}

Context:
{context}

Answer directly without any preamble or reasoning:"""
        
        response = _ollama_generate(model=model, prompt=prompt, timeout=60)
        
        if response:
            # Aggressively clean any thinking/reasoning patterns
            patterns_to_remove = [
                r'^(Alright|Okay|Ok|Let me|I need|I\'ll|I will|Looking|Based on|From what|So,|Well,|Hmm|The user|According to|To answer|I believe|I remember|From the context).*?[.!?]\s*',
                r'^.*?(figure out|extract|identify|find out|asked me|given text|provided context|the context|user is asking).*?[.!?]\s*',
                r'I think.*$',
                r'No other details.*$',
                r'The (text|information|context).*?(says|mentions|states|indicates).*?[.!?]\s*',
                r'^(Here\'s|Here is).*?:\s*',
                r'<think>.*?</think>',  # Remove any thinking tags
                r'\*\*Answer:\*\*\s*',
            ]
            for pattern in patterns_to_remove:
                response = re.sub(pattern, '', response, flags=re.IGNORECASE | re.DOTALL)
            
            response = _strip_urls(response)
            response = re.sub(r"^\s*[-*•]\s*", "", response, flags=re.MULTILINE)
            response = re.sub(r"\n+", " ", response)
            response = response.strip()
            
            # Keep more sentences for complete answers
            sentences = re.split(r'(?<=[.!?])\s+', response)
            response = ' '.join(sentences[:5]).strip()
            
            if response:
                return f"{response}\n\n**Source: {source_label}**"
    
    # Fallback to heuristic if LLM fails or not specified
    heuristic_answer = _heuristic_summarize(query, chunks)
    return f"{heuristic_answer}\n\n**Source: {source_label}**"
