# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**Groundtruth AI** — a citation-grounded customer support copilot for regulated industries (Finance, Healthcare), built as a FastAPI backend + Streamlit UI, using a LangGraph-based agent pipeline: KB retrieval first, web search fallback, with local Ollama LLMs (or a heuristic fallback) for summarization — no cloud LLM dependency required. The local-LLM-only architecture is a deliberate positioning choice: customer data never leaves the deployment, which matters for finance/healthcare buyers.

Previously scoped as a 3-domain demo including Google Pixel device support; that domain was dropped (IP/employer-ownership reasons) and the product now focuses exclusively on Finance + Healthcare.

**Never mix knowledge between domains.** Finance and Healthcare each have fully isolated KB dirs and vector indexes (see [Multi-domain KB](#multi-domain-kb-configdomainsjson)) — a query for one domain must never retrieve from, or be answered using, another domain's KB content.

## Coding conventions

- Type hints on new/edited functions.
- Prefer `pathlib.Path` over `os.path` (existing `os.path` usage, e.g. in `retriever.py`/`main.py`, can stay unless you're already touching that code).
- Prefer async APIs (the FastAPI layer is async end-to-end; keep new endpoints/IO async-compatible).
- Note: the repo currently uses `pip` + `requirements.txt` (not `uv`), and has no Black/Ruff config committed — match existing formatting by hand rather than assuming a formatter/linter will run.

## Commands

```powershell
# Setup
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run API (from repo root)
uvicorn apps.pixel_copilot_api.main:app --reload --port 8000

# Run UI (separate terminal, after activating venv)
$env:COPILOT_API_BASE = "http://127.0.0.1:8000"
streamlit run apps\pixel_copilot_ui\app.py

# Rebuild a domain's KB index (domain: finance | healthcare)
python -m core.rag.retriever rebuild finance
python -m core.rag.retriever rebuild finance ollama:nomic-embed-text   # explicit embed backend

# Query a domain's KB index directly (debugging retrieval/confidence)
python -m core.rag.retriever query finance "how to build an emergency fund"

# Legacy/general debug CLI (operates on default KB_DIR/data/kb, not the per-domain dirs) —
# note: the legacy data/kb/ directory was removed along with the pixel domain, so this CLI
# needs KB_DIR pointed at a real directory (or files added under data/kb/) before it will work.
python debug_kb_query.py "your query"
python debug_kb_query.py --rebuild ollama:nomic-embed-text
python debug_kb_query.py --info
python debug_kb_query.py --test

# Generate synthetic KB content for a domain
python tools/generate_finance_kb.py
python tools/generate_healthcare_kb.py
```

There is no configured lint/format/test tooling (no pytest suite, no linter config) — verify changes by exercising the API/UI directly (see `/verify` skill) or via the retriever debug commands above.

### Optional environment variables
- `TAVILY_API_KEY` — enables web search fallback (without it, web search returns empty results and the agent falls back to KB-no-answer / general-knowledge LLM answer).
- `OLLAMA_HOST` — defaults to `http://localhost:11434`; needed for any `ollama:*` summarizer or embedding backend.
- `EMBED_BACKEND` — `hash` (default, no dependencies) or `ollama:<model>` (e.g. `ollama:nomic-embed-text`). The index must be rebuilt when this changes; retrieval always re-embeds queries using whatever backend the *loaded index* was built with (`meta.embed_backend`), not necessarily the current env var.
- `KB_DIR` / `INDEX_DIR` — legacy single-domain paths (used by `/upload` and `/reindex` API endpoints, and `debug_kb_query.py`). Per-domain paths come from `config/domains.json` instead.
- `MEMORY_DB_PATH` — SQLite path for chat/memory store (default `data/memory/memory.db`).
- `ALLOWED_WEB_DOMAINS` — comma-separated allowlist restricting Tavily results; empty = allow all.
- `MEMORY_DEBUG=true` — verbose logging for memory injection/store code paths.

## Architecture

### Request flow (LangGraph state machine)

`core/graph/graph.py` wires the pipeline; `core/graph/nodes.py` implements each node. All nodes take/return a plain `dict` state (LangGraph optional — if `langgraph` isn't importable, a hand-rolled `_Compiled` shim in `graph.py` replicates the same routing logic sequentially, so both paths must be kept in sync when editing routing).

```
intake -> kb_retrieve -> [route_after_kb] -> answer_from_kb -> policy_gate -> END
                                           -> kb_no_answer   -> policy_gate -> END
                                           -> research_plan -> web_research -> synthesize_research -> policy_gate -> END
```

`route_after_kb` decides the branch: KB confidence >= (intent-adjusted) threshold -> answer from KB; below threshold and web disabled -> `kb_no_answer`; below threshold and web enabled (or `force_research`) -> web research branch.

Key behaviors baked into `nodes.py` worth knowing before touching it:
- **Video-first intent detection**: if the query looks like a YouTube request (`_is_video_request_intent`) and `youtube_enabled` is set, YouTube suggestions short-circuit the KB/web answer entirely (in every branch — `answer_from_kb`, `kb_no_answer`, and `synthesize_research`).
- **YouTube is always auxiliary/non-blocking** otherwise — fetched via `_get_youtube_nonblocking` with a hard timeout (3–5s) and silently dropped on failure; it must never delay or break the main answer.
- **General-knowledge LLM fallback**: when KB and web both fail, `_is_general_knowledge_question` + `_general_knowledge_answer` let the local Ollama model answer from its own knowledge (labeled `**Source: Model Knowledge**`) rather than returning a hard "I don't know".
- **Intent-adjusted KB threshold** (`_apply_intent_thresholds`): sensitive queries (factory reset/wipe) raise the confidence bar; "how to"/"enable"/"turn on" queries lower it.
- Per-node answer caching (`_ANSWER_CACHE`) exists but is disabled via `_CACHE_ENABLED = False` — intentionally, to always get fresh LLM output.
- **Citations/trust tagging**: every payload dict carries `citations` (built by `_build_citations()` from `kb_hits`/`web_snippets`, whichever is in scope) and a `source` marker (`"kb"`, `"web"`, `"general_knowledge"`, `"youtube"`, or `"none"`). The `source` field is what lets the UI distinguish grounded answers from ungrounded ones — treat it as load-bearing for the trust story, not cosmetic. When adding new answer paths, always populate both fields rather than defaulting to empty/`"unknown"`.

### Multi-domain KB (`config/domains.json`)

Two domains — `finance`, `healthcare` — each with its own KB directory (`data/kb_finance`, etc.) and its own vector index (`data/index_finance/index.json`, etc.), fully isolated. `core/rag/retriever.py` resolves domain -> paths via `_load_domain_config()`. The `domain` field flows from the API request all the way through graph state into `kb_retrieve`. There's also a legacy non-domain-scoped `KB_DIR`/`INDEX_DIR` pair used only by the `/upload` and `/reindex` API endpoints and `debug_kb_query.py` — don't conflate the two path schemes.

### RAG retrieval (`core/rag/retriever.py`)

- Chunking (`_smart_chunk`) respects paragraph/markdown-header/sentence boundaries (`CHUNK_SIZE=600` chars, `CHUNK_OVERLAP=100` chars) rather than naive fixed-size splitting.
- Embeddings: `hash` backend (deterministic bag-of-words hashing, zero dependencies, default) or `ollama:<model>` (real embeddings via Ollama's `/api/embeddings`, falls back to hash on error). The backend is stored in the index's `meta.embed_backend` and reused for query-time embedding so index and query vectors stay compatible even if the env var changes later.
- Optional keyword-overlap reranking (`_rerank`) blends embedding cosine score (70%) with token overlap (30%); off by default, toggled via request's `rerank` flag.
- `kb_retrieve_with_confidence` returns `(hits, confidence)` where confidence is the mean of top-k cosine scores, capped at 0.98 — this confidence is what `route_after_kb` compares against the threshold.
- Index auto-builds on first load if missing (`_load_index`); `/upload` and `/reindex` API endpoints force a rebuild.

### Memory system (additive, isolated)

`core/memory/store.py` provides two independent SQLite-backed stores (single db file, `data/memory/memory.db`):
- `ChatStore` — full chat session history (ChatGPT-style), used by the UI's chat sidebar.
- `MemoryStore` — long-term facts/preferences + chat summaries, separate from raw chat history.

`core/memory/context_builder.py` builds a memory-context string injected into agent state via `_inject_memory_context` in `nodes.py`'s `intake` node — explicitly designed as **additive-only**: it must never mutate existing state keys, only add new `_memory_*` prefixed ones, and must degrade gracefully (try/except) if the memory module is unavailable. `apps/pixel_copilot_api/memory_routes.py` exposes this under the API's `/memory` prefix and is likewise additive to `main.py`'s core `/chat` behavior.

### API surface (`apps/pixel_copilot_api/main.py`)

- `POST /chat` / `GET /chat_stream` (SSE) — both build the same graph `state` dict and invoke `agent.ainvoke(state)`; keep their state-construction logic in sync when adding new fields.
- `POST /upload` — validates extension and 10MB size cap, saves under `KB_DIR` with a UUID filename, then immediately rebuilds the (legacy, non-domain-scoped) index.
- `POST /reindex` — rebuilds the legacy index on demand.
- Request-time overrides of `embed_backend`/`kb_threshold` are pushed into `os.environ`, which affects retrieval globally for the process (not request-scoped) — be aware of this when changing concurrent-request behavior.
- `summarizer_model` and `embed_backend` are both validated against explicit allowlists (`ALLOWED_SUMMARIZER_MODELS`, `ALLOWED_EMBED_BACKENDS`) in `ChatRequest.model_post_init`.

### Safety

`core/safety/policies.py`'s `requires_human_review` is a simple keyword-match gate (`SENSITIVE_INTENTS`) run as the final `policy_gate` node on every branch; it appends `policy_flags` to the response rather than blocking the answer.

## Before modifying code

Read and understand, in this order, before changing behavior: the graph flow (`core/graph/graph.py`, `core/graph/nodes.py`), the retrieval pipeline (`core/rag/retriever.py`), memory injection (`core/memory/context_builder.py`, `_inject_memory_context` in `nodes.py`), and the API routes (`apps/pixel_copilot_api/main.py`, `memory_routes.py`). These are tightly coupled through the shared graph `state` dict — a change in one usually has implications in the others.

Do not refactor working retrieval logic (`core/rag/retriever.py` chunking/embedding/scoring) unless explicitly requested.

## Testing changes

There's no automated test suite — after every change, verify manually:
- Run the API locally and exercise `/chat` (or `/chat_stream`) for both domains (finance, healthcare) to confirm no cross-domain leakage.
- Test `/upload` with a real file and confirm reindex picks it up.
- Test memory endpoints (`/memory/*`) — chat creation, message add, retrieval.
- Confirm `citations` and `source` are populated correctly in KB and web-research answers, and that `source` correctly falls back to `"general_knowledge"`/`"none"` when nothing is grounded.

## Rules

- Never hardcode API keys or secrets — use env vars (see [Optional environment variables](#optional-environment-variables)).
- Never modify production configs.
- Never delete vector indexes (`data/index_*`) without explicit instruction — rebuilding is expensive and destructive to in-place state.
- Never break backward compatibility of the `/chat`, `/chat_stream`, or `/memory/*` API contracts.
