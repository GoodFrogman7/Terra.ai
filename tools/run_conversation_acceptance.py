"""Exercise a live multi-turn Research conversation against the configured Ollama model."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.graph.graph import compiled


def invoke(query: str, messages: List[Dict[str, str]], model: str, strict_mode: bool, youtube_enabled: bool) -> Dict[str, Any]:
    return compiled.invoke(
        {
            "query": query,
            "messages": messages,
            "domain": "finance",
            "embed_backend": "hash",
            "force_research": False,
            "rerank": True,
            "KB_THRESHOLD": 0.42,
            "web_enabled": False,
            "youtube_enabled": youtube_enabled,
            "summarizer_model": model,
            "strict_mode": strict_mode,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the multi-turn Research-mode acceptance test.")
    parser.add_argument("--model", default="llama3.1:8b")
    args = parser.parse_args()

    first_question = "Suggest YouTube videos about Virat Kohli"
    first = invoke(first_question, [], args.model, strict_mode=False, youtube_enabled=True)
    history = [
        {"role": "user", "content": first_question},
        {"role": "assistant", "content": first.get("answer", "")},
    ]
    second_question = "who is he"
    second = invoke(second_question, [*history, {"role": "user", "content": second_question}], args.model, strict_mode=False, youtube_enabled=True)
    third_question = "What are some of his biggest achievements?"
    third_history = [
        *history,
        {"role": "user", "content": second_question},
        {"role": "assistant", "content": second.get("answer", "")},
    ]
    third = invoke(third_question, [*third_history, {"role": "user", "content": third_question}], args.model, strict_mode=False, youtube_enabled=True)
    policy = invoke("What is the institution's wire transfer exception procedure?", [], args.model, strict_mode=True, youtube_enabled=False)

    checks = {
        "video_turn_has_suggestions": first.get("source") == "youtube" and bool(first.get("youtube_suggestions")),
        "video_turn_has_answer": "virat" in first.get("answer", "").lower() and len(first.get("answer", "")) > 80,
        "follow_up_uses_context": second.get("source") == "general_knowledge" and "virat" in second.get("answer", "").lower(),
        "follow_up_has_no_videos": not second.get("youtube_suggestions"),
        "second_follow_up_uses_context": third.get("source") == "general_knowledge" and "virat" in third.get("answer", "").lower(),
        "second_follow_up_has_no_videos": not third.get("youtube_suggestions"),
        "research_answer_has_no_unverified_freshness_claim": not any(
            term in first.get("answer", "").lower()
            for term in ("current", "captain", "ceo", "president", "prime minister")
        ),
        "policy_mode_refuses_unknown": policy.get("source") == "none" and not policy.get("citations"),
    }
    print(json.dumps({"checks": checks, "first": first, "second": second, "third": third, "policy": policy}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
