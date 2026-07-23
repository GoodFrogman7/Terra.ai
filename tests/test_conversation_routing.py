"""Conversation-routing regressions for Research mode."""
from core.graph import nodes
from core.graph.nodes import intake, kb_no_answer


def test_follow_up_does_not_inherit_video_intent_from_history():
    history = [
        {"role": "user", "content": "Suggest YouTube videos about Virat Kohli"},
        {"role": "assistant", "content": "Virat Kohli is an Indian cricketer."},
        {"role": "user", "content": "who is he"},
    ]
    result = intake(
        {
            "query": "who is he",
            "messages": history,
            "domain": "finance",
            "youtube_enabled": True,
            "strict_mode": False,
            "KB_THRESHOLD": 0.42,
        }
    )
    assert result["query"] == "Who is Virat Kohli?"
    assert result["_is_video_request"] is False
    assert "_video_query" not in result


def test_possessive_follow_up_keeps_the_prior_subject():
    history = [
        {"role": "user", "content": "Suggest YouTube videos about Virat Kohli"},
        {"role": "assistant", "content": "Virat Kohli is an Indian cricketer."},
        {"role": "user", "content": "What are some of his biggest achievements?"},
    ]
    result = intake(
        {
            "query": "What are some of his biggest achievements?",
            "messages": history,
            "domain": "finance",
            "youtube_enabled": True,
            "strict_mode": False,
            "KB_THRESHOLD": 0.42,
        }
    )
    assert result["query"].endswith("(about Virat Kohli)")
    assert result["_is_video_request"] is False


def test_video_request_extracts_subject_from_current_message_only():
    result = intake(
        {
            "query": "Suggest YouTube videos about Virat Kohli",
            "messages": [],
            "domain": "finance",
            "youtube_enabled": True,
            "strict_mode": False,
            "KB_THRESHOLD": 0.42,
        }
    )
    assert result["_is_video_request"] is True
    assert result["_video_query"] == "Virat Kohli"


def test_video_request_contains_a_short_answer_and_suggestions(monkeypatch):
    suggestions = [{"video_id": "abc", "title": "Virat Kohli interview"}]
    monkeypatch.setattr(nodes, "_get_youtube_nonblocking", lambda *args, **kwargs: suggestions)
    monkeypatch.setattr(nodes, "_research_model_answer", lambda *args, **kwargs: "Virat Kohli is an Indian cricketer.")

    result = kb_no_answer(
        {
            "query": "Suggest YouTube videos about Virat Kohli",
            "_is_video_request": True,
            "_video_query": "Virat Kohli",
            "youtube_enabled": True,
            "strict_mode": False,
            "messages": [],
            "summarizer_model": "llama3.1:8b",
        }
    )
    assert result["source"] == "youtube"
    assert result["youtube_suggestions"] == suggestions
    assert "Virat Kohli is an Indian cricketer." in result["answer"]
    assert "relevant YouTube videos" in result["answer"]


def test_research_fallback_uses_conversational_model(monkeypatch):
    monkeypatch.setattr(nodes, "_research_model_answer", lambda *args, **kwargs: "Virat Kohli is an Indian cricketer.")
    result = kb_no_answer(
        {
            "query": "Who is Virat Kohli?",
            "youtube_enabled": True,
            "strict_mode": False,
            "messages": [],
            "summarizer_model": "llama3.1:8b",
        }
    )
    assert result["source"] == "general_knowledge"
    assert result["answer"] == "Virat Kohli is an Indian cricketer."
    assert result["youtube_suggestions"] == []


def test_time_sensitive_question_never_falls_back_to_model_memory(monkeypatch):
    def unexpected_model_call(*args, **kwargs):
        raise AssertionError("Time-sensitive questions must not use model-only fallback")

    monkeypatch.setattr(nodes, "_research_model_answer", unexpected_model_call)
    result = kb_no_answer(
        {
            "query": "How did Oliver Tree pass away?",
            "youtube_enabled": True,
            "strict_mode": False,
            "web_enabled": False,
            "messages": [],
            "summarizer_model": "llama3.1:8b",
        }
    )
    assert result["source"] == "none"
    assert "won't guess" in result["answer"]


def test_web_answer_is_grounded_and_does_not_attach_videos(monkeypatch):
    monkeypatch.setattr(
        nodes,
        "_grounded_web_answer",
        lambda *args, **kwargs: "Oliver Tree died in a helicopter collision.",
    )
    monkeypatch.setattr(
        nodes,
        "_get_youtube_nonblocking",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Videos are only fetched for video requests")),
    )
    result = nodes.synthesize_research(
        {
            "query": "How did Oliver Tree pass away?",
            "web_snippets": [
                {
                    "title": "BBC",
                    "url": "https://www.bbc.com/news/example",
                    "snippet": "Oliver Tree died when the helicopter he was travelling in collided with another in Brazil.",
                }
            ],
            "web_conf": 0.6,
            "youtube_enabled": True,
            "strict_mode": False,
            "summarizer_model": "llama3.1:8b",
        }
    )
    assert result["source"] == "web"
    assert "helicopter collision" in result["answer"]
    assert result["citations"]
    assert result["youtube_suggestions"] == []


def test_web_event_cleanup_removes_vague_collision_filler():
    answer = nodes._clean_vague_event_wording(
        "Oliver Tree passed away when the helicopter he was in collided with something, "
        "resulting in his death along with five others. The exact details of the collision "
        "are not specified in the provided excerpts."
    )
    assert "helicopter collision" in answer
    assert "something" not in answer
    assert "exact details" not in answer.lower()
