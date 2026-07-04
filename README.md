# Terra.ai (Ollama-only LLMs)

A grounded, citation-backed AI support assistant for regulated industries (finance, healthcare) — runs entirely on local/free LLMs (Ollama), so customer data never leaves your infrastructure.

- KB-first retrieval with confidence-based routing to web search, then general-model fallback — every answer is tagged with its source (KB / web / general knowledge) so ungrounded answers are never presented as verified fact
- Web Search toggle (KB-only mode when disabled)
- LLM summarization via **Ollama** (llama3.1:8b, mistral:7b, gemma3:4b) or **none** (heuristic fallback)
- Upload to KB (PDF/MD/TXT/CSV/JSON). Auto-index on first query.
- Conversational chat, re-ranking, caching, intent thresholds, graph viz

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
