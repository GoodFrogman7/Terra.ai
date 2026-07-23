# Architecture

## Runtime Shape

```text
Streamlit UI -> FastAPI -> graph intake -> KB retrieval -> answer or approved web research
                    |                         |                    |
                    |                         -> SQLite analytics   -> citations and source label
                    -> SQLite chat history
```

## Components

- `apps/ui/app.py`: Streamlit chat experience. `DEMO_MODE` presents the finance-first Terra Policy Desk surface; development mode retains both domains and engineering controls.
- `apps/api/main.py`: FastAPI API for chat, streaming chat, upload, reindex, configuration, analytics, auth, and memory routes.
- `core/graph`: routing pipeline. A LangGraph graph is used when installed; a sequential compatibility implementation keeps local operation working without it.
- `core/rag/retriever.py`: document loading, PDF extraction, chunking, indexing, retrieval, evidence-aware reranking, and confidence calculation.
- `core/tools/web_search.py`: Tavily integration. Searches only run when requested and returned sources are filtered to `ALLOWED_WEB_DOMAINS` when configured.
- `core/analytics/store.py`: SQLite interaction telemetry scoped by `user_id`.
- `core/memory`: SQLite chat and memory stores. Chat persistence works; memory injection is not yet wired into synthesis prompts.
- `core/auth/supabase_auth.py`: optional Supabase JWT authentication. Unconfigured local mode uses the `local` user.

## Answer Contract

Every answer response carries `answer`, `source`, `citations`, and `policy_flags`.

- `source=kb` and `source=web` require at least one citation.
- Hash-based KB results require meaningful query-term overlap; multi-term queries require at least two shared terms.
- A missing or unapproved web result returns `source=none` or the explicitly labeled model-knowledge path; it is never presented as Web evidence.
- External web research is disabled by default.

## Data Boundaries

- Finance and healthcare have separate KB and index directories configured in `config/domains.json`.
- Analytics reads are scoped to the authenticated user. This is not yet organization-level isolation.
- Uploaded content is stored in the selected KB directory and an index is rebuilt synchronously.

## Production Direction

Keep the current monolith for a small paid pilot. Before broader rollout, move ingestion to a job queue, store document/index versions in durable object storage and a relational database, introduce organization and role access control, and send structured events to centralized observability.
