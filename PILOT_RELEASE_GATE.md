# Pilot Release Gate

Terra Policy Desk is eligible for a paid pilot only after the customer-specific strict-mode evaluation passes. The bundled finance articles and smoke cases are development fixtures, not a substitute for the customer's policies or a market claim.

## Required Inputs

- At least 100 de-identified, customer-authored staff questions covering the agreed policy libraries.
- A named policy owner has approved each source document, effective date, and expected outcome.
- Every answer case identifies the policy source and an answer point that appears in that source.
- Every abstention case is intentional and has an escalation or review destination outside the assistant.

## Automated Gate

Run:

```powershell
.\.venv311\Scripts\python.exe tools\run_pilot_evaluation.py --input evaluations\customer_pilot_100.jsonl --require-100 --report reports\pilot-evaluation.json
```

The run fails if there are fewer than 100 cases, if any answer is uncited or non-extractive, if an expected source is missing, or if an expected abstention returns an answer. Archive the exact corpus, source-library version, application commit, and JSON report together.

## Human Gate

- A policy owner reviews every failed case and a representative sample of passed answers against the original document.
- Any critical wrong answer, stale policy, cross-customer leak, or broken access control blocks release until it is fixed and re-evaluated.
- The pilot agreement names the supported libraries, approval workflow, escalation owner, retention period, and outage contact.

Strict mode reduces unsupported generation by refusing to answer without retrieved evidence. It cannot guarantee that an approved source is correct, current, complete, or appropriately interpreted; the customer owns those source controls.
