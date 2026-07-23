# Decisions

## 2026-07-22 - Finance-first, staff-facing launch

Decision: launch Terra Policy Desk for internal policy support at community banks and credit unions.

Why: it has a clear buyer, a bounded source corpus, visible ROI in answer consistency and lookup time, and lower safety/compliance exposure than consumer financial advice or healthcare deployment.

Consequences: demo mode presents finance only; healthcare code and data remain available for development but are not the sales story.

## 2026-07-22 - Evidence over fallback fluency

Decision: a KB or Web source label requires citations. Empty web research falls back to an explicit no-answer or model-knowledge path.

Why: frontline policy support must make uncertainty visible.

Consequences: more abstentions are acceptable; pilot evaluation should measure useful abstention separately from wrong answers.

## 2026-07-22 - Hash embeddings are pilot-only with an evidence guard

Decision: retain the dependency-free hash backend for pilot setup, but require meaningful overlap and route on strongest grounded evidence.

Why: it makes the existing product safer immediately without introducing infrastructure.

Consequences: paraphrase recall is limited. A real embedding model and customer evaluation set are prerequisites for broader rollout.

## 2026-07-22 - External web is opt-in

Decision: external research is disabled by default and source filtering is enforceable through `ALLOWED_WEB_DOMAINS`.

Why: a question can be sensitive and web results need controlled provenance.

Consequences: pilot teams must deliberately configure approved sources before enabling research.

## 2026-07-22 - Keep the monolith through the paid proof of value

Decision: do not introduce a queue, vector database, or microservices before a pilot validates workflow and willingness to pay.

Why: the current system is simple enough to operate while the product question is still open.

Consequences: production rollout requires a dedicated ingestion and tenancy architecture.
