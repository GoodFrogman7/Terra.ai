import os, requests
from typing import Dict, Any, List


def _get_allowed_domains() -> set:
    """Get allowed domains dynamically (not cached at module load)."""
    domains = os.getenv("ALLOWED_WEB_DOMAINS", "").strip()
    if not domains:
        return set()  # Empty = allow all
    return {d.strip() for d in domains.split(",") if d.strip()}


def _ok(url: str) -> bool:
    allowed = _get_allowed_domains()
    if not allowed:
        return True
    return any(url.startswith(f"https://{d}") or url.startswith(f"http://{d}") for d in allowed)


def web_search_bundle(query: str) -> Dict[str, Any]:
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not tavily_key:
        print("[WEB_SEARCH] No TAVILY_API_KEY set")
        return {"snippets": [], "confidence": 0.0}
    try:
        print(f"[WEB_SEARCH] Searching for: {query}")
        r = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": tavily_key, "query": query, "max_results": 8, "include_answer": False},
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        print(f"[WEB_SEARCH] Got {len(data.get('results', []))} results")
    except Exception as e:
        print(f"[WEB_SEARCH] Error: {e}")
        return {"snippets": [], "confidence": 0.0}

    results = data.get("results", [])
    kept: List[Dict[str, Any]] = []
    allowed_hits = 0
    for item in results:
        url = item.get("url", "")
        if _ok(url):
            allowed_hits += 1
        kept.append({
            "title": item.get("title", "web"),
            "url": url,
            "snippet": item.get("content", "")[:1200]
        })
    conf = 0.55 + 0.1 * (allowed_hits / max(1, len(results))) if results else 0.0
    return {"snippets": kept, "confidence": min(conf, 0.92)}
