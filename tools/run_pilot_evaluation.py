"""Run strict-mode policy-assistant acceptance cases against the local graph."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.graph.graph import compiled


def load_cases(path: Path) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_number}: {exc.msg}") from exc
        if not case.get("id") or not case.get("question") or case.get("expected") not in {"answer", "abstain"}:
            raise ValueError(f"Case on line {line_number} needs id, question, and expected=answer|abstain")
        cases.append(case)
    return cases


def evaluate_case(case: Dict[str, Any]) -> Dict[str, Any]:
    state = {
        "query": case["question"],
        "messages": [],
        "domain": case.get("domain", "finance"),
        "embed_backend": "hash",
        "force_research": False,
        "rerank": True,
        "KB_THRESHOLD": case.get("kb_threshold"),
        "web_enabled": bool(case.get("web_enabled", False)),
        "youtube_enabled": False,
        "summarizer_model": "none",
        "strict_mode": True,
    }
    final = compiled.invoke(state)
    answer = final.get("answer", "")
    citations = final.get("citations", [])
    source = final.get("source", "unknown")
    strict_evidence = final.get("_strict_evidence", [])
    expected = case["expected"]
    failures: List[str] = []

    if expected == "answer":
        if source not in {"kb", "web"}:
            failures.append(f"expected a source-backed answer, got source={source}")
        if not citations:
            failures.append("source-backed answer has no citations")
        if not strict_evidence:
            failures.append("source-backed answer was not marked extractive")
        actual_titles = {citation.get("title") for citation in citations}
        for title in case.get("expected_source_titles", []):
            if title not in actual_titles:
                failures.append(f"missing expected source title: {title}")
        answer_lower = answer.lower()
        for phrase in case.get("required_phrases", []):
            if phrase.lower() not in answer_lower:
                failures.append(f"missing required phrase: {phrase}")
    else:
        if source != "none":
            failures.append(f"expected abstention, got source={source}")
        if citations:
            failures.append("abstention included citations")
        if strict_evidence:
            failures.append("abstention included extractive evidence")

    return {
        "id": case["id"],
        "question": case["question"],
        "expected": expected,
        "passed": not failures,
        "failures": failures,
        "answer": answer,
        "source": source,
        "citations": citations,
    }


def evaluate_cases(cases: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    results = [evaluate_case(case) for case in cases]
    return results, sum(1 for result in results if result["passed"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate strict, source-backed policy answers.")
    parser.add_argument("--input", type=Path, default=ROOT / "evaluations" / "finance_pilot_smoke.jsonl")
    parser.add_argument("--report", type=Path, help="Optional JSON report path")
    parser.add_argument("--min-cases", type=int, default=1, help="Fail if the corpus has fewer cases")
    parser.add_argument("--require-100", action="store_true", help="Apply the paid-pilot 100-case minimum")
    args = parser.parse_args()

    cases = load_cases(args.input)
    minimum = max(args.min_cases, 100 if args.require_100 else 0)
    if len(cases) < minimum:
        print(f"FAIL: {args.input} contains {len(cases)} cases; the gate requires at least {minimum}.")
        return 2

    results, passed = evaluate_cases(cases)
    report = {
        "input": str(args.input),
        "strict_mode": True,
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        details = "" if result["passed"] else f" - {'; '.join(result['failures'])}"
        print(f"{status} {result['id']}{details}")
    print(f"{passed}/{len(results)} cases passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
