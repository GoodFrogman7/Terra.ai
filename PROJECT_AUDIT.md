# Project Audit

Updated: 2026-07-22

## Product Snapshot

Terra.ai is a FastAPI and Streamlit retrieval assistant with finance and healthcare knowledge bases, optional local Ollama models, SQLite-backed chat and analytics data, optional Supabase authentication, and an optional Tavily web fallback.

The launch focus is now a finance-first internal policy assistant for community banks and credit unions. Healthcare remains supported in the codebase but is not the public launch promise.

## Verified Findings

- The finance and healthcare indexes are physically separated by configuration and retrieval path.
- A hash embedding backend is the default and a LangGraph-compatible sequential fallback runs when LangGraph is absent.
- PDF uploads previously indexed only a placeholder filename; uploads now extract text with `pypdf` and reject unreadable or scanned-only PDFs.
- Retrieval confidence previously averaged candidate cosine scores. This could reject relevant answers and allow accidental hash collisions. Hash retrieval now requires meaningful query overlap and routes on the strongest grounded hit.
- Web search was enabled by default and its allowlist did not actually filter returned results. It is now opt-in, and only configured domains are returned.
- The web branch could label an answer as Web without citations. Grounded labels now require citations.
- Analytics stored `user_id` but aggregate and recent queries were not scoped by it. Those reads now filter by the current user.
- Chat persistence exists, but the injected memory context is not yet consumed by answer-generation prompts. The current UI should be understood as saved chat history, not reliable long-term personalized memory.

## Current Strengths

- Small, understandable deployment footprint for a pilot.
- Citation objects flow through the API and UI.
- Domain-specific upload and indexing paths are already present.
- The API has payload limits, rate limiting, request-scoped model settings, and local-mode development.
- The codebase has an automated test suite and CI-friendly deterministic fallback behavior.

## Launch Gaps

### P0 - Resolved in this baseline

- Grounded hash retrieval, source-label integrity, approved-domain web filtering, PDF extraction, and tenant-scoped analytics.

### P1 - Required before production financial-institution rollout

- Organization, role, and document-level authorization instead of user-only scoping.
- An evaluation set made from each pilot customer's real policy questions, with a review workflow and release gate.
- Background ingestion jobs, index versioning, failure status, and retry behavior.
- Durable audit events for uploads, questions, answers, source access, and configuration changes.
- Encryption, retention/deletion controls, backups, and an incident-response runbook.

### P2 - Important product improvements

- A reviewer console for documents, sources, feedback, and unanswered questions.
- Explicit answer freshness and source-effective-date metadata.
- Chat cancellation, progress states, and upload/reindex status.
- Structured policy metadata such as product, procedure, owner, effective date, and approval state.

## Launch Recommendation

Sell a paid proof of value, not a broad "AI for finance" platform. Limit the first scope to up to 25 internal staff, three approved policy libraries, and source-linked answers. Do not position the pilot as customer-facing advice, a core-banking integration, legal/compliance automation, or a HIPAA-ready healthcare product.
