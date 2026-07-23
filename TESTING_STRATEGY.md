# Testing Strategy

## Goals

Protect the answer trust contract, tenant boundaries, and ingestion behavior while keeping local development deterministic and independent of Ollama or web credentials.

## Automated Coverage

- Retriever unit tests: deterministic embeddings, chunking, finance/healthcare isolation, meaningful-overlap guard, and PDF text extraction.
- Graph tests: strict answers are extractive and cited, no-answer paths are explicitly labeled, and sensitive prompts are flagged.
- API tests: validation, uploads, streaming contract, defaults, rate limits, and no environment leakage from request overrides.
- Web tests: allowlisted hostnames are retained and lookalike/unapproved domains are excluded.
- Analytics tests: summaries and recent events are scoped to the caller's user id.

Run locally:

```powershell
.\.venv311\Scripts\python.exe -m pytest tests -q
.\.venv311\Scripts\python.exe -m compileall apps core tools -q
.\.venv311\Scripts\python.exe tools\run_pilot_evaluation.py
.\.venv311\Scripts\python.exe tools\run_conversation_acceptance.py --model llama3.1:8b
```

## Conversation Acceptance

The live-model acceptance script verifies a three-turn Research conversation: a video request includes both a short answer and suggestions, a pronoun follow-up retains the subject without repeating video cards, and strict Policy mode refuses an unsupported policy question. Run it whenever conversational routing or model configuration changes.

## Pilot Evaluation Set

Before each paid pilot release, create at least 100 real, de-identified questions across the agreed policy libraries. For each, record the expected source, source-backed answer points, escalation expectation, and effective-date requirements. The development smoke corpus is not sufficient for this gate.

Release criteria:

- The strict evaluation runner passes with `--require-100` and 100% of answer cases are cited and extractive.
- 0 known cross-tenant or cross-library source leaks.
- No critical wrong-answer finding in review.
- Measured answer correctness and citation usefulness meet the jointly agreed pilot target.
- Unanswered questions are reviewable and tracked.

## Manual Checks

- Upload a text PDF and a scanned/unreadable PDF; only the extractable document may index.
- Test the default UI with web disabled, then enable web with a restrictive allowlist.
- Exercise finance and healthcare developer domains independently.
- Review mobile and desktop Streamlit layouts before customer demos.
- Run a restore drill for SQLite backups before storing customer data.
