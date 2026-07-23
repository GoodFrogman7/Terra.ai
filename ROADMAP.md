# Roadmap

## P0 - Paid Pilot Foundation

### Trustworthy answers

- Problem: hash collisions and averaged confidence could produce an irrelevant route or reject a relevant answer.
- Evidence: finance and healthcare cross-domain probes returned cosine candidates despite no sufficient evidence.
- User impact: staff could receive a confident but wrong policy answer.
- Solution: meaningful-term grounding, evidence-based confidence, cited-source invariant.
- Systems: retriever, graph nodes, API tests.
- Dependencies: none.
- Risk: exact-term guard can abstain on paraphrases; use real embeddings and an evaluation set in the pilot.
- Complexity: medium.
- Acceptance: approved finance questions return cited KB results; off-domain probes abstain.
- Verification: `pytest tests -q` plus customer evaluation set.

### Safe external research

- Problem: external research was on by default and allowlisted domains were not enforced.
- Evidence: web result loop retained non-allowlisted results.
- User impact: unnecessary data egress and unreviewed citations.
- Solution: opt-in web setting and strict hostname filtering.
- Systems: UI, API defaults, web tool.
- Dependencies: Tavily key and an approved source list for each pilot.
- Risk: fewer fallback answers; that is preferable to unsupported claims.
- Complexity: small.
- Acceptance: no default web request; only approved hostnames appear when enabled.
- Verification: unit test with approved and rejected hostnames.

## P1 - Reliable Customer Core

### Tenant and document authorization

- Problem: user-scoped analytics is not organization, role, or document-level authorization.
- Evidence: no organization model or source permission filters exist.
- User impact: unacceptable access boundary for a financial-institution rollout.
- Solution: organization, membership, role, document ACL, and permission-aware retrieval models.
- Systems: auth, storage, API, retrieval metadata, UI administration.
- Dependencies: selected production identity provider and database.
- Risk: data migration and authorization mistakes.
- Complexity: large.
- Acceptance: a user cannot enumerate, retrieve, cite, or observe another tenant's document or telemetry.
- Verification: authorization integration tests and a security review.

### Managed ingestion and source lifecycle

- Problem: uploads synchronously rebuild indexes with no status, version, or retry model.
- Evidence: `/upload` and `/reindex` perform work in request time.
- User impact: slow requests and uncertain source freshness.
- Solution: queued ingest jobs, versioned documents/indexes, status UI, retries, and effective-date metadata.
- Systems: upload API, worker, storage, UI.
- Dependencies: durable database, object storage, queue.
- Risk: operational complexity.
- Complexity: large.
- Acceptance: upload returns a job id, reports progress/failure, and only serves the last successful index.
- Verification: job lifecycle and recovery tests.

## P2 - Operations Console

Build a review queue for unanswered questions, feedback, source gaps, policy owner approval, and answer-quality metrics. Add cancellation/progress states, audit views, and structured source metadata. Verify with staff usability sessions and evaluator agreement.

## P3 - Differentiation

Add policy-change impact analysis, role-aware answer templates, escalation handoffs, and integrations with approved document systems. Ship only after permissions, audit logging, and evaluations are mature.

## P4 - Experiments

Consider customer-safe workflow assistants that draft a handoff or checklist from cited policies. Keep them human-approved and never authorize autonomous financial decisions.
