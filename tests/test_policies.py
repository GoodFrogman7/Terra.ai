"""Tests for the policy gate keyword matcher."""
from core.safety.policies import SENSITIVE_INTENTS, requires_human_review


def test_sensitive_intents_are_flagged():
    for intent in SENSITIVE_INTENTS:
        flags = requires_human_review({"query": f"I want to {intent} right now"})
        assert flags == [f"escalate:{intent}"]


def test_benign_query_has_no_flags():
    assert requires_human_review({"query": "how do I build an emergency fund"}) == []


def test_missing_query_is_safe():
    assert requires_human_review({}) == []
