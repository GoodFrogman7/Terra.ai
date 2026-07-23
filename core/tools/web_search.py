import os
import base64
import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

import requests


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
    hostname = (urlparse(url).hostname or "").lower()
    return any(hostname == domain.lower() or hostname.endswith(f".{domain.lower()}") for domain in allowed)


class _DuckDuckGoResultsParser(HTMLParser):
    """Small dependency-free parser for DuckDuckGo's server-rendered results."""

    def __init__(self) -> None:
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._field = ""
        self._field_tag = ""

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            url = _decode_duckduckgo_url(attributes.get("href") or "")
            self.results.append({"title": "", "url": url, "snippet": ""})
            self._field = "title"
            self._field_tag = tag
        elif "result__snippet" in classes and self.results:
            self._field = "snippet"
            self._field_tag = tag

    def handle_endtag(self, tag: str) -> None:
        if self._field and tag == self._field_tag:
            self._field = ""
            self._field_tag = ""

    def handle_data(self, data: str) -> None:
        if self._field and self.results:
            self.results[-1][self._field] += data


def _decode_duckduckgo_url(href: str) -> str:
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urlparse(href)
    redirected = parse_qs(parsed.query).get("uddg", [""])[0]
    return unquote(redirected or href)


class _BingResultsParser(HTMLParser):
    """Extract organic result title, destination, and caption from Bing HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._result: Optional[Dict[str, str]] = None
        self._in_heading = False
        self._in_caption = False
        self._field = ""
        self._field_tag = ""

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "li" and "b_algo" in classes:
            self._result = {"title": "", "url": "", "snippet": ""}
            self._in_heading = False
            self._in_caption = False
            return
        if not self._result:
            return
        if tag == "h2":
            self._in_heading = True
        elif tag == "a" and self._in_heading:
            self._result["url"] = _decode_bing_url(attributes.get("href") or "")
            self._field = "title"
            self._field_tag = tag
        elif tag == "div" and "b_caption" in classes:
            self._in_caption = True
        elif tag == "p" and self._in_caption:
            self._field = "snippet"
            self._field_tag = tag

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2":
            self._in_heading = False
        elif tag == "div" and self._in_caption:
            self._in_caption = False
        elif tag == "li" and self._result:
            if self._result["title"] and self._result["url"]:
                self.results.append(self._result)
            self._result = None
            self._field = ""
            self._field_tag = ""
        if self._field and tag == self._field_tag:
            self._field = ""
            self._field_tag = ""

    def handle_data(self, data: str) -> None:
        if self._field and self._result:
            self._result[self._field] += data


def _decode_bing_url(href: str) -> str:
    parsed = urlparse(href)
    encoded = parse_qs(parsed.query).get("u", [""])[0]
    if encoded.startswith("a1"):
        try:
            payload = encoded[2:]
            return base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            pass
    return href


def _filter_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    kept: List[Dict[str, Any]] = []
    for item in results:
        url = item.get("url", "")
        if not url or not _ok(url):
            continue
        snippet = " ".join(str(item.get("snippet", "")).split())
        title = " ".join(str(item.get("title", "web")).split()) or "web"
        if snippet:
            kept.append({"title": title, "url": url, "snippet": snippet[:1200]})
    # Keep search ordering within a trust tier, but surface official and established
    # reporting first when a current-event answer is being grounded.
    preferred_domains = {
        "apnews.com", "bbc.com", "reuters.com", "npr.org", "wmg.com",
        "nytimes.com", "washingtonpost.com", "latimes.com", "theguardian.com",
        "usatoday.com", "usnews.com",
    }

    def quality(item: Dict[str, Any]) -> int:
        host = (urlparse(item["url"]).hostname or "").lower()
        if host.endswith(".gov") or host.endswith(".edu"):
            return 0
        if any(host == domain or host.endswith(f".{domain}") for domain in preferred_domains):
            return 0
        return 1

    return sorted(kept, key=quality)


def _normalize_search_query(query: str) -> str:
    """Turn the graph's private follow-up annotation into a normal web query."""
    match = re.search(r"\s*\(about\s+([^)]+)\)\s*$", query or "", flags=re.IGNORECASE)
    if not match:
        return query
    subject = match.group(1).strip()
    request = (query or "")[:match.start()].strip()
    return f"{subject} {request}".strip()


def _search_tavily(query: str, api_key: str) -> Tuple[List[Dict[str, Any]], str]:
    try:
        print(f"[WEB_SEARCH] Searching for: {query}")
        r = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": 8, "include_answer": False},
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        print(f"[WEB_SEARCH] Got {len(data.get('results', []))} results")
    except Exception as e:
        return [], f"Tavily search failed: {e}"

    return _filter_results(
        [
            {"title": item.get("title", "web"), "url": item.get("url", ""), "snippet": item.get("content", "")}
            for item in data.get("results", [])
        ]
    ), ""


def _search_duckduckgo(query: str) -> Tuple[List[Dict[str, Any]], str]:
    """Use a no-key provider when a hosted search key is not configured."""
    try:
        response = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (compatible; TerraResearch/1.0)"},
            timeout=12,
        )
        response.raise_for_status()
        parser = _DuckDuckGoResultsParser()
        parser.feed(response.text)
    except Exception as e:
        return [], f"DuckDuckGo search failed: {e}"
    return _filter_results(parser.results), ""


def _search_bing(query: str) -> Tuple[List[Dict[str, Any]], str]:
    try:
        response = requests.get(
            "https://www.bing.com/search",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (compatible; TerraResearch/1.0)"},
            timeout=12,
        )
        response.raise_for_status()
        parser = _BingResultsParser()
        parser.feed(response.text)
    except Exception as e:
        return [], f"Bing search failed: {e}"
    return _filter_results(parser.results), ""


def web_search_bundle(query: str) -> Dict[str, Any]:
    """Return search evidence with a provider label and an explicit failure state."""
    query = _normalize_search_query(query)
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    errors: List[str] = []
    if tavily_key:
        tavily_results, tavily_error = _search_tavily(query, tavily_key)
        if tavily_results:
            return {"snippets": tavily_results, "confidence": 0.72, "provider": "tavily", "error": ""}
        if tavily_error:
            errors.append(tavily_error)

    bing_results, bing_error = _search_bing(query)
    if bing_results:
        return {"snippets": bing_results, "confidence": 0.6, "provider": "bing", "error": ""}
    if bing_error:
        errors.append(bing_error)

    duckduckgo_results, duckduckgo_error = _search_duckduckgo(query)
    if duckduckgo_results:
        return {"snippets": duckduckgo_results, "confidence": 0.6, "provider": "duckduckgo", "error": ""}
    if duckduckgo_error:
        errors.append(duckduckgo_error)
    return {
        "snippets": [],
        "confidence": 0.0,
        "provider": "none",
        "error": "; ".join(errors) or "No live web results were available.",
    }
