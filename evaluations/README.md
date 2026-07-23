# Pilot Evaluation Corpus

`finance_pilot_smoke.jsonl` is a small deterministic smoke suite. It verifies that strict mode returns an extractive, cited answer for known content and abstains when evidence is absent. It is not a launch-validation corpus.

Create a customer-specific JSONL file with at least 100 de-identified questions before a paid pilot. Each line requires `id`, `question`, and `expected` (`answer` or `abstain`). Answer cases can additionally require the expected source filename and phrases a reviewer must see in the source excerpt.

Run the smoke suite:

```powershell
.\.venv311\Scripts\python.exe tools\run_pilot_evaluation.py
```

Apply the paid-pilot cardinality gate and save its report:

```powershell
.\.venv311\Scripts\python.exe tools\run_pilot_evaluation.py --input evaluations\customer_pilot_100.jsonl --require-100 --report reports\pilot-evaluation.json
```

Every source document and every expected answer must be approved by the customer policy owner. Do not generate expected answers from the assistant being tested.
