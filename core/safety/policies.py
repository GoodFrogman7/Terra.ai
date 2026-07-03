from typing import Dict, Any, List

SENSITIVE_INTENTS = ["delete account", "factory reset", "legal", "privacy complaint"]

def requires_human_review(state: Dict[str, Any]) -> List[str]:
    q = (state.get("query") or "").lower()
    flags = []
    for intent in SENSITIVE_INTENTS:
        if intent in q:
            flags.append(f"escalate:{intent}")
    return flags
