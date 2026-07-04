from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
import os, json, time, shutil, uuid
from pathlib import Path
from dotenv import load_dotenv
from core.rag.retriever import build_index, INDEX_PATH
load_dotenv()

from core.graph.graph import compiled as agent

app = FastAPI(title="Terra.ai API")

# Include memory routes (additive - does not modify existing behavior)
from apps.api.memory_routes import router as memory_router
app.include_router(memory_router)

from core.analytics.store import get_analytics_store

def _log_interaction(final: Dict[str, Any], domain: str, query: str) -> None:
    """Record interaction metrics; never raises."""
    get_analytics_store().log_interaction(
        domain=domain,
        source=final.get("source", "unknown"),
        kb_conf=final.get("kb_conf"),
        num_citations=len(final.get("citations", [])),
        policy_flags=final.get("policy_flags", []),
        query_chars=len(query or ""),
    )
KB_ROOT = Path(os.getenv("KB_DIR","data/kb")).resolve()
KB_ROOT.mkdir(parents=True, exist_ok=True)

os.environ["KB_DIR"] = str(KB_ROOT)
os.environ["INDEX_DIR"] = str(Path("data/index").resolve())

class Message(BaseModel):
    role: str
    content: str

ALLOWED_EMBED_BACKENDS = {"hash", "ollama:nomic-embed-text", "ollama:mxbai-embed-large", "ollama:qwen3-embedding:8b"}
ALLOWED_SUMMARIZER_MODELS = {"none", "llama3.2", "deepseek-r1:1.5b", "llama3.1:8b", "mistral:7b", "gemma3:4b"}

class ChatRequest(BaseModel):
    user_id: Optional[str] = Field(None, max_length=128)
    message: str = Field(..., min_length=1, max_length=10_000)
    messages: List[Message] = Field(default_factory=list)
    domain: Literal["finance", "healthcare"] = "finance"
    kb_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    research_only: Optional[bool] = None
    rerank: Optional[bool] = None
    embed_backend: Optional[str] = Field(None, max_length=64)
    web_enabled: Optional[bool] = None
    youtube_enabled: Optional[bool] = None
    summarizer_model: Optional[str] = Field(None, max_length=64)

    def model_post_init(self, __context):
        if self.embed_backend and self.embed_backend not in ALLOWED_EMBED_BACKENDS:
            raise ValueError(f"embed_backend must be one of {ALLOWED_EMBED_BACKENDS}")
        if self.summarizer_model and self.summarizer_model not in ALLOWED_SUMMARIZER_MODELS:
            raise ValueError(f"summarizer_model must be one of {ALLOWED_SUMMARIZER_MODELS}")

class YouTubeSuggestion(BaseModel):
    video_id: str
    title: str
    channel_name: str = ""
    thumbnail_url: str
    video_url: str

class ChatResponse(BaseModel):
    answer: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    source: str = "unknown"
    policy_flags: List[str] = Field(default_factory=list)
    youtube_suggestions: List[YouTubeSuggestion] = Field(default_factory=list)

@app.get("/healthz")
def healthz():
    return {"ok": True, "kb_dir": str(KB_ROOT)}

@app.get("/analytics/summary")
def analytics_summary(domain: Optional[str] = None):
    """Aggregate resolution/grounding metrics for the dashboard."""
    store = get_analytics_store()
    return {"summary": store.summary(domain=domain), "recent": store.recent(limit=50)}

@app.get("/config")
def get_config():
    """Single source of truth for UI dropdowns: domains, models, backends."""
    domains_path = Path("config/domains.json")
    domains = {}
    if domains_path.exists():
        domains = json.loads(domains_path.read_text(encoding="utf-8"))
    return {
        "domains": {k: {"name": v.get("name", k), "description": v.get("description", "")} for k, v in domains.items()},
        "summarizer_models": sorted(ALLOWED_SUMMARIZER_MODELS),
        "embed_backends": sorted(ALLOWED_EMBED_BACKENDS),
    }

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    suffix_ok = {".md",".markdown",".txt",".csv",".json",".pdf"}
    ext = Path(file.filename).suffix.lower()
    if ext not in suffix_ok:
        return {"ok": False, "msg": f"Unsupported extension {ext}"}
    safe_name = f"{uuid.uuid4().hex}{ext}"
    target = KB_ROOT / safe_name
    size = 0
    with target.open("wb") as f:
        while chunk := file.file.read(8192):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                target.unlink(missing_ok=True)
                return {"ok": False, "msg": "File exceeds 10MB limit"}
            f.write(chunk)

    # NEW: build/refresh index immediately
    idx = build_index(os.environ["KB_DIR"], os.path.join(os.environ["INDEX_DIR"], "index.json"))
    return {"ok": True, "path": str(target), "indexed_docs": len(idx.get("entries", []))}

@app.post("/reindex")
def reindex():
    idx = build_index(os.environ["KB_DIR"], os.path.join(os.environ["INDEX_DIR"], "index.json"))
    return {"ok": True, "indexed_docs": len(idx.get("entries", []))}

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if req.kb_threshold is not None:
        os.environ["KB_CONFIDENCE_THRESHOLD"] = str(req.kb_threshold)
    if req.embed_backend:
        os.environ["EMBED_BACKEND"] = req.embed_backend

    state = {
        "query": req.message,
        "messages": [m.model_dump() for m in req.messages],
        "user_id": req.user_id,
        "domain": req.domain,
        "force_research": bool(req.research_only),
        "rerank": bool(req.rerank),
        "KB_THRESHOLD": float(req.kb_threshold) if req.kb_threshold is not None else 0.45,
        "web_enabled": True if req.web_enabled is None else bool(req.web_enabled),
        "youtube_enabled": bool(req.youtube_enabled) if req.youtube_enabled else False,
        "summarizer_model": (req.summarizer_model or "none"),
    }
    final = await agent.ainvoke(state)
    _log_interaction(final, req.domain, req.message)
    return ChatResponse(
        answer=final.get("answer",""),
        citations=final.get("citations",[]),
        source=final.get("source","unknown"),
        policy_flags=final.get("policy_flags",[]),
        youtube_suggestions=final.get("youtube_suggestions",[]),
    )

@app.get("/chat_stream")
async def chat_stream(
    request: Request,
    user_id: Optional[str] = None,
    message: str = "",
    domain: str = "finance",  # finance, healthcare
    kb_threshold: Optional[float] = None,
    research_only: Optional[bool] = None,
    rerank: Optional[bool] = None,
    embed_backend: Optional[str] = None,
    web_enabled: Optional[bool] = None,
    youtube_enabled: Optional[bool] = None,
    summarizer_model: Optional[str] = None,
    history: Optional[str] = None,
):
    def sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    try:
        if kb_threshold is not None:
            os.environ["KB_CONFIDENCE_THRESHOLD"] = str(kb_threshold)
        if embed_backend:
            os.environ["EMBED_BACKEND"] = embed_backend

        messages = []
        if history:
            try:
                messages = json.loads(history)
            except Exception:
                messages = []

        state = {
            "query": message,
            "messages": messages,
            "user_id": user_id,
            "domain": domain,  # NEW: pass domain to agent
            "force_research": bool(research_only),
            "rerank": bool(rerank),
            "KB_THRESHOLD": float(kb_threshold) if kb_threshold is not None else 0.45,
            "web_enabled": True if web_enabled is None else bool(web_enabled),
            "youtube_enabled": bool(youtube_enabled) if youtube_enabled else False,
            "summarizer_model": (summarizer_model or "none"),
        }
        final = await agent.ainvoke(state)
        _log_interaction(final, domain, message)
        full = final.get("answer","")
        citations = final.get("citations",[])
        source = final.get("source","unknown")
        policy_flags = final.get("policy_flags",[])
        youtube_suggestions = final.get("youtube_suggestions",[])

        def gen():
            step = 48
            for i in range(0, len(full), step):
                yield sse({"delta": full[i:i+step]})
                time.sleep(0.02)
            yield sse({"done": True, "citations": citations, "source": source, "policy_flags": policy_flags, "youtube_suggestions": youtube_suggestions})
        return StreamingResponse(gen(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    except Exception as e:
        def gen_err():
            yield sse({"delta": f"⚠️ {type(e).__name__}: {str(e)}"})
            yield sse({"done": True, "citations": [], "policy_flags": ["api_error"]})
        return StreamingResponse(gen_err(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
