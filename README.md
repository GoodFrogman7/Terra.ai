# Terra.ai (Ollama-only LLMs)

## Launch Direction

Terra Policy Desk is the finance-first paid-pilot surface for this codebase: source-linked internal policy support for community banks and credit unions. The healthcare domain remains available for development, but it is not the launch offer. See [PRODUCT_VISION.md](PRODUCT_VISION.md), [ROADMAP.md](ROADMAP.md), and [SECURITY_AND_SCALE.md](SECURITY_AND_SCALE.md) before presenting this as a production service.

Policy mode is strict by default: it returns selected wording from cited, approved sources and refuses when it cannot retrieve evidence. Research mode restores broader discovery controls, including YouTube suggestions and optional approved-web research; it is deliberately distinct from policy answers. External web research is disabled by default; when enabled, the question is sent to the configured research provider, and `ALLOWED_WEB_DOMAINS` should contain the customer-approved source hosts.

A grounded, citation-backed AI support assistant for finance and healthcare. Local Ollama models are optional; any enabled web research sends the question to the configured research provider.

- KB-first retrieval with confidence-based routing to web search, then general-model fallback — every answer is tagged with its source (KB / web / general knowledge) so ungrounded answers are never presented as verified fact
- Web Search toggle (KB-only mode when disabled)
- LLM summarization via **Ollama** (llama3.1:8b, mistral:7b, gemma3:4b) or **none** (heuristic fallback)
- Upload to KB (PDF/MD/TXT/CSV/JSON). Auto-index on first query.
- Conversational chat, re-ranking, caching, intent thresholds, graph viz
- Analytics dashboard (grounded-answer rate, citation rate, escalations) at the "Analytics" page in the UI
- Optional multi-user auth via Supabase: set `SUPABASE_URL` + `SUPABASE_ANON_KEY` in `.env` and every user gets isolated chats/memories behind email+password login; leave unset for single-user local mode

## Run with Docker (recommended)
```bash
docker compose up --build -d
# First run only: pull the local models
docker compose exec ollama ollama pull llama3.2
docker compose exec ollama ollama pull nomic-embed-text
```
UI at http://localhost:8501, API at http://localhost:8000. Optional: put `TAVILY_API_KEY=...` in a `.env` file to enable web-search fallback.

Run verification with `pytest tests -q`. Run `python tools/run_pilot_evaluation.py` for the deterministic smoke corpus. The paid-pilot 100-case gate is documented in [PILOT_RELEASE_GATE.md](PILOT_RELEASE_GATE.md). The finance-first demo is enabled with `DEMO_MODE=true`.

## Run (Windows PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Optional: enable Tavily web search
# $env:TAVILY_API_KEY = "tvly-..."

# Optional: run Ollama locally for LLM summarization and embeddings
# Download and start Ollama, then:
# $env:OLLAMA_HOST = "http://localhost:11434"
# In UI, pick a summarizer LLM (or choose "none" to use heuristic)

# Start API
uvicorn apps.api.main:app --reload --port 8000

# Start UI (new terminal)
.\.venv\Scripts\Activate.ps1
$env:COPILOT_API_BASE = "http://127.0.0.1:8000"
streamlit run apps\ui\app.py
```

### Notes
- If Ollama is not running or the selected model is not pulled, the app will fall back to a deterministic heuristic summary.
- Supported summarizer choices in UI:
  - none (heuristic)
  - ollama:llama3.1:8b
  - ollama:mistral:7b
  - ollama:gemma3:4b
- Embeddings can also come from Ollama (qwen3-embedding:8b, etc.) via the embedding backend selector.
- Domains: **Finance** and **Healthcare**, each with an isolated knowledge base and vector index — domains never share KB content.
