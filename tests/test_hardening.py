"""Regression tests for the finance-first trust and tenant-isolation baseline."""
from pathlib import Path

from core.analytics.store import AnalyticsStore
from core.graph.nodes import policy_gate, synthesize_research
from core.rag import retriever
from core.rag.retriever import kb_retrieve_with_confidence
from core.tools import web_search


def test_hash_retrieval_rejects_off_domain_question():
    hits, confidence = kb_retrieve_with_confidence(
        "how do I build an emergency fund", k=3, rerank=True, domain="healthcare"
    )
    assert hits == []
    assert confidence == 0.0


def test_default_hash_retrieval_is_grounded_for_finance():
    hits, confidence = kb_retrieve_with_confidence(
        "how do I build an emergency fund", k=3, rerank=True, domain="finance"
    )
    assert hits
    assert confidence >= 0.42
    assert all(hit["keyword_overlap"] > 0 for hit in hits)


def test_pdf_text_is_extracted(monkeypatch, tmp_path: Path):
    class FakePage:
        def extract_text(self):
            return "Wire transfers require dual approval."

    class FakeReader:
        def __init__(self, _path):
            self.pages = [FakePage()]

    pdf = tmp_path / "policy.pdf"
    pdf.write_bytes(b"not a real PDF")
    monkeypatch.setattr(retriever, "PdfReader", FakeReader)
    assert retriever.load_document_text(pdf) == "Wire transfers require dual approval."


def test_web_search_only_returns_approved_domains(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {"title": "Approved", "url": "https://sub.example.com/policy", "content": "approved"},
                    {"title": "Unapproved", "url": "https://example.evil.com/policy", "content": "unapproved"},
                ]
            }

    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setenv("ALLOWED_WEB_DOMAINS", "example.com")
    monkeypatch.setattr(web_search.requests, "post", lambda *args, **kwargs: FakeResponse())

    result = web_search.web_search_bundle("wire policy")
    assert result["confidence"] > 0
    assert [item["title"] for item in result["snippets"]] == ["Approved"]


def test_follow_up_annotation_becomes_a_natural_web_query():
    assert web_search._normalize_search_query("how did he pass away (about Oliver Tree)") == "Oliver Tree how did he pass away"


def test_empty_web_result_never_claims_web_source():
    result = synthesize_research({"query": "account policy", "web_snippets": [], "summarizer_model": "none"})
    assert result["source"] == "none"
    assert result["citations"] == []
    assert "**(Web)**" not in result["answer"]


def test_policy_gate_removes_grounded_label_without_citations():
    result = policy_gate({"query": "account policy", "source": "web", "citations": [], "answer": "ungrounded"})
    assert result["source"] == "none"
    assert result["citations"] == []


def test_analytics_are_scoped_to_the_current_user(tmp_path: Path):
    store = AnalyticsStore(tmp_path / "analytics.db")
    store.log_interaction("finance", "kb", kb_conf=0.8, num_citations=1, user_id="member-a")
    store.log_interaction("healthcare", "web", kb_conf=0.6, num_citations=1, user_id="member-b")

    summary = store.summary(user_id="member-a")
    recent = store.recent(user_id="member-a")
    assert summary["total_interactions"] == 1
    assert summary["by_domain"] == {"finance": 1}
    assert len(recent) == 1
    assert recent[0]["domain"] == "finance"
