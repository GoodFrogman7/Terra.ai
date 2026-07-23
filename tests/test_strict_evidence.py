"""Strict pilot-mode tests: source excerpts or refusal, never model fallback."""
from core.graph import nodes
from core.graph.nodes import answer_from_kb, kb_no_answer, policy_gate, synthesize_research


def _wire_transfer_hit():
    return {
        "title": "wire_transfer_policy.md",
        "url": "kb://finance/wire_transfer_policy.md",
        "content": "# Wire Transfer Procedure\n\nWire transfers require dual approval from Operations and Compliance.",
        "score": 0.94,
    }


def test_strict_kb_answer_is_extractive_and_never_summarizes(monkeypatch):
    monkeypatch.setattr(nodes, "summarize", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not summarize")))
    result = answer_from_kb(
        {
            "query": "Who approves wire transfers?",
            "kb_hits": [_wire_transfer_hit()],
            "strict_mode": True,
            "youtube_enabled": False,
        }
    )
    assert result["source"] == "kb"
    assert result["citations"]
    assert result["_strict_evidence"]
    assert "Wire transfers require dual approval from Operations and Compliance." in result["answer"]


def test_strict_no_answer_never_uses_model_knowledge(monkeypatch):
    monkeypatch.setattr(nodes, "_general_knowledge_answer", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not use model knowledge")))
    result = kb_no_answer({"query": "Who is the president of the United States?", "strict_mode": True})
    assert result["source"] == "none"
    assert result["citations"] == []
    assert result["answer"] == "I cannot verify that in the approved sources."


def test_research_mode_can_return_youtube_suggestions(monkeypatch):
    suggestions = [{"video_id": "TKOvXajAhbA", "title": "Virat Kohli video"}]
    monkeypatch.setattr(nodes, "_get_youtube_nonblocking", lambda *args, **kwargs: suggestions)
    result = kb_no_answer(
        {
            "query": "suggest YouTube videos about Virat Kohli",
            "_is_video_request": True,
            "_video_query": "Virat Kohli",
            "youtube_enabled": True,
            "strict_mode": False,
        }
    )
    assert result["source"] == "youtube"
    assert result["youtube_suggestions"] == suggestions


def test_strict_web_answer_is_extractive_and_cited(monkeypatch):
    monkeypatch.setattr(nodes, "summarize", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not summarize")))
    result = synthesize_research(
        {
            "query": "What is the wire transfer procedure?",
            "web_conf": 0.9,
            "web_snippets": [
                {
                    "title": "Approved policy",
                    "url": "https://approved.example/policy",
                    "snippet": "Wire transfer procedure: Staff must verify the member before submitting a transfer.",
                }
            ],
            "strict_mode": True,
            "youtube_enabled": False,
        }
    )
    assert result["source"] == "web"
    assert result["citations"]
    assert result["_strict_evidence"]
    assert "Staff must verify the member" in result["answer"]


def test_policy_gate_rejects_strict_answer_without_extractive_evidence():
    result = policy_gate(
        {
            "query": "wire transfer procedure",
            "answer": "ungrounded",
            "source": "kb",
            "citations": [_wire_transfer_hit()],
            "strict_mode": True,
        }
    )
    assert result["source"] == "none"
    assert "strict_evidence_rejected" in result["policy_flags"]
