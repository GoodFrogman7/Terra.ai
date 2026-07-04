"""End-to-end graph pipeline tests (no network: web/youtube disabled, heuristic summarizer)."""
import asyncio
from typing import Any, Dict

from core.graph.graph import compiled as agent


def _base_state(query: str, domain: str, **overrides: Any) -> Dict[str, Any]:
    state = {
        "query": query,
        "messages": [],
        "domain": domain,
        "force_research": False,
        "rerank": True,
        "KB_THRESHOLD": 0.05,
        "web_enabled": False,
        "youtube_enabled": False,
        "summarizer_model": "none",
    }
    state.update(overrides)
    return state


def _invoke(state: Dict[str, Any]) -> Dict[str, Any]:
    return asyncio.run(agent.ainvoke(state))


def test_finance_kb_answer_is_grounded():
    r = _invoke(_base_state("how do I build an emergency fund", "finance"))
    assert r["source"] == "kb"
    assert r["citations"], "KB answers must carry citations"
    assert all("kb_finance" in c.get("url", c.get("id", "")) for c in r["citations"])
    assert r["answer"].strip()


def test_healthcare_kb_answer_is_grounded():
    r = _invoke(_base_state("when should I see a doctor about a fever", "healthcare"))
    assert r["source"] == "kb"
    assert r["citations"]
    assert all("kb_healthcare" in c.get("url", c.get("id", "")) for c in r["citations"])


def test_no_answer_path_populates_source_and_empty_citations():
    """Below-threshold KB + web disabled must yield an ungrounded-but-labeled result."""
    r = _invoke(_base_state("zxqv blorptastic frimble", "finance", KB_THRESHOLD=0.99))
    assert r["source"] in {"none", "general_knowledge"}
    assert r["citations"] == []


def test_policy_gate_flags_sensitive_query():
    r = _invoke(_base_state("I have a privacy complaint about my account", "finance", KB_THRESHOLD=0.99))
    assert "escalate:privacy complaint" in r.get("policy_flags", [])
