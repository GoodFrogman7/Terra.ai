"""Manual live acceptance check for the current-events safety contract."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.graph.graph import compiled


def main() -> int:
    result = compiled.invoke(
        {
            "query": "how did he pass away",
            "messages": [
                {"role": "user", "content": "who is oliver tree"},
                {"role": "assistant", "content": "Oliver Tree was a singer."},
            ],
            "domain": "finance",
            "KB_THRESHOLD": 0.42,
            "web_enabled": True,
            "youtube_enabled": True,
            "strict_mode": False,
            "summarizer_model": "llama3.1:8b",
            "embed_backend": "hash",
        }
    )
    answer = str(result.get("answer", "")).lower()
    checks = {
        "follow_up_resolved": "oliver tree" in str(result.get("query", "")).lower(),
        "uses_live_web": result.get("source") == "web",
        "has_citations": bool(result.get("citations")),
        "explains_death": "helicopter" in answer and ("died" in answer or "death" in answer or "pass away" in answer),
        "uses_concrete_event_wording": "collided with something" not in answer and "helicopter" in answer,
        "does_not_attach_videos": not result.get("youtube_suggestions"),
    }
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    if not all(checks.values()):
        print(result)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
