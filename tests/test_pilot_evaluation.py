from pathlib import Path

from tools.run_pilot_evaluation import evaluate_cases, load_cases


def test_smoke_evaluation_cases_pass_in_strict_mode():
    cases = load_cases(Path("evaluations/finance_pilot_smoke.jsonl"))
    results, passed = evaluate_cases(cases)
    assert len(results) == 4
    assert passed == len(results)
    assert all(result["passed"] for result in results)
