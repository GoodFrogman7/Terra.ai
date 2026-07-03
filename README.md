# Customer Support Copilot v4 (Ollama-only LLMs)

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
uvicorn apps.pixel_copilot_api.main:app --reload --port 8000

# Start UI (new terminal)
.\.venv\Scripts\Activate.ps1
$env:COPILOT_API_BASE = "http://127.0.0.1:8000"
streamlit run apps\pixel_copilot_ui\app.py
```

### Notes
- If Ollama is not running or the selected model is not pulled, the app will fall back to a deterministic heuristic summary.
- Supported summarizer choices in UI:
  - none (heuristic)
  - ollama:llama3.1:8b
  - ollama:mistral:7b
  - ollama:gemma3:4b
- Embeddings can also come from Ollama (qwen3-embedding:8b, etc.) via the embedding backend selector.
