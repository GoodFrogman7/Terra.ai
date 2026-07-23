"""
KB Retriever Module
- Loads and indexes KB files from domain-specific directories
- Supports hash and ollama embedding backends
- Improved chunking with overlap for better semantic matching
- Multi-domain support (finance, healthcare)
"""
import os
import json
import re
import hashlib
from pathlib import Path
from typing import List, Dict, Tuple, Optional

try:
    from pypdf import PdfReader
except ImportError:  # The API surfaces a clear upload error until dependencies are installed.
    PdfReader = None

# Domain configuration loader
def _load_domain_config() -> dict:
    """Load domain configuration from config/domains.json"""
    config_path = Path("config/domains.json")
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    # Fallback if config doesn't exist
    return {
        "finance": {"kb_dir": "data/kb_finance", "index_dir": "data/index_finance"},
        "healthcare": {"kb_dir": "data/kb_healthcare", "index_dir": "data/index_healthcare"}
    }

def _get_kb_dir(domain: str = "finance") -> str:
    """Get KB directory for a specific domain."""
    config = _load_domain_config()
    return config.get(domain, {}).get("kb_dir", f"data/kb_{domain}")

def _get_index_dir(domain: str = "finance") -> str:
    """Get index directory for a specific domain."""
    config = _load_domain_config()
    return config.get(domain, {}).get("index_dir", f"data/index_{domain}")

def _get_index_path(domain: str = "finance") -> str:
    """Get index file path for a specific domain."""
    return os.path.join(_get_index_dir(domain), "index.json")

# Legacy configuration (for backward compatibility)
KB_DIR = os.getenv("KB_DIR", "data/kb")
INDEX_DIR = os.getenv("INDEX_DIR", "data/index")
INDEX_PATH = os.path.join(INDEX_DIR, "index.json")

# Chunking settings (optimized for semantic retrieval)
CHUNK_SIZE = 600       # ~150-200 words / ~200-250 tokens
CHUNK_OVERLAP = 100    # ~25-40 tokens overlap for context continuity


def _get_embed_backend() -> str:
    """Get embedding backend dynamically (not cached at module load)."""
    return os.getenv("EMBED_BACKEND", "hash").strip()


def _get_ollama_host() -> str:
    """Get Ollama host dynamically."""
    host = os.getenv("OLLAMA_HOST", "").strip()
    return host if host else "http://localhost:11434"


def _tokenize(text: str) -> List[str]:
    """Simple word tokenization for reranking."""
    return re.findall(r"[A-Za-z0-9]+", (text or "").lower())


_QUERY_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "about", "be", "basic", "basics", "best",
    "build", "by", "can", "could", "do", "does", "for", "from", "get", "give", "help",
    "how", "i", "in", "is", "it", "learn", "make", "me", "my", "need", "of", "on",
    "or", "please", "see", "should", "start", "tell", "that", "the", "their", "this", "tips",
    "to", "use", "want", "was", "what", "when", "where", "which", "who", "why", "with",
    "would", "you", "your",
}


def _meaningful_tokens(text: str) -> set[str]:
    """Return terms suitable for checking that a hash retrieval is grounded."""
    return {token for token in _tokenize(text) if len(token) > 1 and token not in _QUERY_STOP_WORDS}


def _token_bucket(tok: str, dim: int) -> int:
    """Deterministic token->bucket mapping. Built-in hash() is salted per
    process (PYTHONHASHSEED), which would make index vectors incompatible
    with query vectors from any other process."""
    return int.from_bytes(hashlib.md5(tok.encode("utf-8")).digest()[:8], "big") % dim


def _hash_embed(text: str, dim: int = 512) -> List[float]:
    """Hash-based bag-of-words embedding (fast, no dependencies)."""
    vec = [0.0] * dim
    for tok in _tokenize(text):
        vec[_token_bucket(tok, dim)] += 1.0
    norm = (sum(v * v for v in vec) ** 0.5) or 1.0
    return [v / norm for v in vec]


def _ollama_embed(text: str, model: str) -> List[float]:
    """Get embeddings from Ollama API."""
    import requests
    host = _get_ollama_host()
    try:
        r = requests.post(
            f"{host}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=30
        )
        r.raise_for_status()
        vec = r.json().get("embedding", [])
        if isinstance(vec, list) and len(vec) > 0:
            norm = (sum(v * v for v in vec) ** 0.5) or 1.0
            return [float(v) / norm for v in vec]
    except Exception as e:
        print(f"[RETRIEVER] Ollama embed error: {e}, falling back to hash")
    return _hash_embed(text, 512)


def _embed(text: str, backend: Optional[str] = None) -> List[float]:
    """Generate embedding vector for text."""
    eb = backend or _get_embed_backend()
    if eb.startswith("ollama:"):
        model = eb.split(":", 1)[1]
        return _ollama_embed(text, model)
    return _hash_embed(text)


def _cos(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def load_document_text(path: Path) -> str:
    """Load extractable text from a supported document without inventing content."""
    suf = path.suffix.lower()
    if suf in {".md", ".markdown", ".txt", ".csv", ".json"}:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
    if suf == ".pdf":
        if PdfReader is None:
            return ""
        try:
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except Exception:
            return ""
    return ""


def _load_text(path: Path) -> str:
    """Backward-compatible internal alias for document text loading."""
    return load_document_text(path)


def _smart_chunk(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Smart chunking that respects sentence/paragraph boundaries.
    - chunk_size: target chunk size in characters (~150-200 words)
    - overlap: characters to overlap between chunks for context
    """
    if not text or not text.strip():
        return []
    
    # Clean up text
    text = re.sub(r'\n{3,}', '\n\n', text)  # Normalize multiple newlines
    text = re.sub(r' {2,}', ' ', text)       # Normalize multiple spaces
    
    # Split by paragraphs first (double newline or markdown headers)
    paragraphs = re.split(r'\n\n+|(?=^#{1,3}\s)', text, flags=re.MULTILINE)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    chunks = []
    current_chunk = ""
    
    for para in paragraphs:
        # If paragraph alone is too big, split by sentences
        if len(para) > chunk_size:
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sent in sentences:
                if len(current_chunk) + len(sent) + 1 <= chunk_size:
                    current_chunk += (" " if current_chunk else "") + sent
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sent
        else:
            # Add paragraph to current chunk
            if len(current_chunk) + len(para) + 2 <= chunk_size:
                current_chunk += ("\n\n" if current_chunk else "") + para
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para
    
    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    # Add overlap between chunks for context continuity
    if overlap > 0 and len(chunks) > 1:
        overlapped_chunks = []
        for i, chunk in enumerate(chunks):
            if i > 0:
                # Prepend end of previous chunk
                prev_overlap = chunks[i - 1][-overlap:] if len(chunks[i - 1]) > overlap else chunks[i - 1]
                # Find a clean break point (space or newline)
                break_point = prev_overlap.find(' ')
                if break_point > 0:
                    prev_overlap = prev_overlap[break_point + 1:]
                chunk = prev_overlap + " " + chunk
            overlapped_chunks.append(chunk.strip())
        return overlapped_chunks
    
    return chunks


def _chunk(text: str, size: int = CHUNK_SIZE) -> List[str]:
    """Legacy chunk function - now uses smart chunking."""
    return _smart_chunk(text, size, CHUNK_OVERLAP)


def build_index(kb_dir: Optional[str] = None, index_path: Optional[str] = None, embed_backend: Optional[str] = None, domain: str = "finance") -> dict:
    """
    Build KB index from all files in kb_dir.
    
    Args:
        kb_dir: Directory containing KB files (default: domain-specific)
        index_path: Where to save the index (default: domain-specific)
        embed_backend: Embedding backend to use (default: from env)
        domain: Domain name (finance, healthcare)
    
    Returns:
        Index dictionary with metadata and entries
    """
    backend = embed_backend or _get_embed_backend()
    kb_dir = kb_dir or _get_kb_dir(domain)
    index_path = index_path or _get_index_path(domain)
    kb_dir_p = Path(kb_dir)
    idx_path = Path(index_path)
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"[RETRIEVER] Building index from {kb_dir}")
    print(f"[RETRIEVER] Embedding backend: {backend}")
    
    # Load all documents
    docs = []
    for p in kb_dir_p.rglob("*"):
        if p.suffix.lower() in {".md", ".markdown", ".txt", ".csv", ".json", ".pdf"}:
            txt = _load_text(p)
            if not txt.strip():
                continue
            docs.append({
                "id": str(p),
                "title": p.name,
                "url": str(p),
                "content": txt
            })
            print(f"[RETRIEVER] Loaded: {p.name} ({len(txt)} chars)")
    
    if not docs:
        raise RuntimeError(f"No KB files found under {kb_dir}")
    
    # Chunk and embed all documents
    entries = []
    for d in docs:
        chunks = _smart_chunk(d["content"])
        print(f"[RETRIEVER] {d['title']}: {len(chunks)} chunks")
        for j, chunk in enumerate(chunks):
            vec = _embed(chunk, backend)
            entries.append({
                "id": f"{d['id']}#c{j}",
                "title": d["title"],
                "url": d["url"],
                "content": chunk,
                "vec": vec
            })
    
    # Save index
    meta = {
        "dim": len(entries[0]["vec"]) if entries else 0,
        "embed_backend": backend,
        "num_docs": len(docs),
        "num_chunks": len(entries),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP
    }
    out = {"meta": meta, "entries": entries}
    idx_path.write_text(json.dumps(out), encoding="utf-8")
    
    print(f"[RETRIEVER] Index built: {len(entries)} chunks from {len(docs)} files")
    print(f"[RETRIEVER] Saved to: {index_path}")
    
    return out


def _load_index(index_path: Optional[str] = None, domain: str = "finance", embed_backend: Optional[str] = None) -> dict:
    """Load index from disk, or build if not exists (embed_backend only affects a fresh build)."""
    index_path = index_path or _get_index_path(domain)
    p = Path(index_path)
    if not p.exists():
        return build_index(domain=domain, embed_backend=embed_backend)
    return json.loads(p.read_text(encoding="utf-8"))


def clear_index(index_path: Optional[str] = None, domain: str = "finance") -> bool:
    """Delete the existing index file."""
    index_path = index_path or _get_index_path(domain)
    p = Path(index_path)
    if p.exists():
        p.unlink()
        print(f"[RETRIEVER] Deleted index: {index_path}")
        return True
    return False


def rebuild_index(kb_dir: Optional[str] = None, index_path: Optional[str] = None, embed_backend: Optional[str] = None, domain: str = "finance") -> dict:
    """Clear and rebuild the KB index."""
    clear_index(domain=domain)
    return build_index(kb_dir, index_path, embed_backend, domain)


def _add_grounding_score(query: str, hit: Dict) -> Dict:
    """Attach a relevance score that requires meaningful evidence, not hash collisions."""
    query_terms = _meaningful_tokens(query)
    document_terms = _meaningful_tokens(hit.get("content", ""))
    overlap = query_terms & document_terms
    coverage = len(overlap) / len(query_terms) if query_terms else 0.0
    cosine = max(0.0, float(hit.get("score", 0.0)))

    # Coverage is intentionally the dominant signal. Hash vectors can collide,
    # so a high cosine without shared meaningful terms is not enough to ground an answer.
    grounding_score = (0.60 * coverage) + (0.25 * min(1.0, len(overlap) / 2.0)) + (0.15 * cosine)
    enriched = dict(hit)
    enriched["cosine_score"] = cosine
    enriched["keyword_overlap"] = len(overlap)
    enriched["query_coverage"] = coverage
    enriched["score"] = min(0.98, grounding_score)
    return enriched


def _rerank(query: str, hits: List[Dict], enabled: bool) -> List[Dict]:
    """Rank by evidence coverage when requested, retaining cosine order otherwise."""
    if not hits:
        return []
    scored = [_add_grounding_score(query, hit) for hit in hits]
    key = (lambda hit: hit["score"]) if enabled else (lambda hit: hit["cosine_score"])
    return sorted(scored, key=key, reverse=True)


def get_default_kb_threshold(domain: str = "finance", embed_backend: Optional[str] = None) -> float:
    """Choose a conservative default calibrated to the active index backend."""
    try:
        backend = _load_index(domain=domain, embed_backend=embed_backend).get("meta", {}).get("embed_backend", "hash")
    except Exception:
        backend = embed_backend or _get_embed_backend()
    return 0.42 if backend == "hash" else 0.55


def kb_retrieve_with_confidence(query: str, k: int = 5, rerank: bool = False, domain: str = "finance", embed_backend: Optional[str] = None) -> Tuple[List[Dict], float]:
    """
    Retrieve top-k KB chunks for a query.

    Args:
        query: Search query
        k: Number of results to return
        rerank: Whether to apply keyword reranking
        domain: Domain name (finance, healthcare)
        embed_backend: Backend used only if the index must be built on the fly;
            queries are always embedded with the loaded index's own backend

    Returns:
        (list of hits, confidence score)
    """
    idx = _load_index(domain=domain, embed_backend=embed_backend)
    
    # Use the same backend that was used to build the index
    index_backend = idx.get("meta", {}).get("embed_backend", "hash")
    qv = _embed(query, index_backend)
    
    # Score all entries
    scored = []
    for e in idx.get("entries", []):
        vec = e.get("vec", [])
        if len(vec) == len(qv):
            s = _cos(qv, vec)
            scored.append((e, s))
    
    if not scored:
        return [], 0.0
    
    # Sort by similarity
    scored.sort(key=lambda t: t[1], reverse=True)
    top_pairs = scored[:max(k * 4, 16)]
    
    # Format hits
    hits = [
        {
            "title": e["title"],
            "url": e["url"],
            "content": e["content"],
            "score": float(s)
        }
        for e, s in top_pairs
    ]
    
    # Hash embeddings are only a candidate generator. Require lexical evidence
    # before returning a hit so accidental bucket collisions cannot look grounded.
    hits = _rerank(query, hits, rerank)
    if index_backend == "hash":
        query_terms = _meaningful_tokens(query)
        min_overlap = 1 if len(query_terms) <= 1 else 2
        hits = [hit for hit in hits if hit["keyword_overlap"] >= min_overlap]
    hits = hits[:k]
    
    if not hits:
        return [], 0.0
    
    # The strongest grounded hit is a useful route signal; averaging unrelated
    # candidates previously made clearly relevant queries look low-confidence.
    conf = min(0.98, max(0.0, float(hits[0]["score"])))
    
    return hits, conf


def debug_query(query: str, k: int = 5, domain: str = "finance") -> None:
    """
    Debug utility to test KB retrieval.
    Prints top-k results with scores and snippets.
    """
    print(f"\n{'='*60}")
    print(f"DEBUG KB QUERY: {query} [Domain: {domain}]")
    print(f"{'='*60}")
    
    idx = _load_index(domain=domain)
    meta = idx.get("meta", {})
    print(f"Index backend: {meta.get('embed_backend', 'unknown')}")
    print(f"Total chunks: {meta.get('num_chunks', len(idx.get('entries', [])))}")
    print(f"Chunk size: {meta.get('chunk_size', 'unknown')}")
    
    hits, conf = kb_retrieve_with_confidence(query, k=k, rerank=True, domain=domain)

    print(f"\nOverall confidence: {conf:.4f}")
    print(f"\nTop {len(hits)} results:")
    print("-" * 60)

    for i, h in enumerate(hits, 1):
        print(f"\n{i}. [{h['score']:.4f}] {h['title']}")
        snippet = h['content'][:200].replace('\n', ' ')
        print(f"   Snippet: {snippet}...")

    print(f"\n{'='*60}\n")


def index_info(domain: str = "finance") -> None:
    """Print index metadata and per-file chunk counts for a domain."""
    print(f"\n{'='*60}")
    print(f"KB INDEX INFO [Domain: {domain}]")
    print(f"{'='*60}")
    idx = _load_index(domain=domain)
    meta = idx.get("meta", {})
    entries = idx.get("entries", [])
    print(f"Index path: {_get_index_path(domain)}")
    print(f"Embedding backend: {meta.get('embed_backend', 'unknown')}")
    print(f"Vector dimension: {meta.get('dim', 'unknown')}")
    print(f"Documents: {meta.get('num_docs', 'unknown')}")
    print(f"Chunks: {meta.get('num_chunks', len(entries))}")
    print(f"Chunk size/overlap: {meta.get('chunk_size', '?')}/{meta.get('chunk_overlap', '?')}")
    files = sorted(set(e.get("title", "") for e in entries))
    print(f"\nSource files ({len(files)}):")
    for f in files:
        count = sum(1 for e in entries if e.get("title") == f)
        print(f"  - {f}: {count} chunks")
    print(f"{'='*60}\n")


_TEST_QUERIES: Dict[str, List[str]] = {
    "finance": [
        "how to build an emergency fund",
        "credit card debt payoff strategies",
        "retirement planning basics",
        "budgeting for beginners",
    ],
    "healthcare": [
        "managing chronic conditions",
        "when to see a doctor",
        "preventive care checklist",
        "medication management tips",
    ],
}


def run_test_suite(domain: str = "finance") -> None:
    """Run canned queries against a domain's index and report confidence spread."""
    queries = _TEST_QUERIES.get(domain, _TEST_QUERIES["finance"])
    print(f"\n{'='*60}")
    print(f"RETRIEVAL TEST SUITE [Domain: {domain}]")
    print(f"{'='*60}")
    confs = []
    for q in queries:
        hits, conf = kb_retrieve_with_confidence(q, k=3, rerank=True, domain=domain)
        confs.append(conf)
        top = hits[0]["title"] if hits else "NO HITS"
        print(f"  [{conf:.3f}] {q}  ->  {top}")
    avg = sum(confs) / len(confs)
    print("-" * 60)
    print(f"Average confidence: {avg:.4f}")
    if avg >= 0.4:
        print(f"Retrieval looks healthy. Suggested threshold: {max(0.3, avg - 0.15):.2f}-{avg:.2f}")
    else:
        print("Low confidence — consider rebuilding with real embeddings:")
        print(f"  python -m core.rag.retriever rebuild {domain} ollama:nomic-embed-text")
    print(f"{'='*60}\n")


# CLI entry point
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "rebuild":
        domain = sys.argv[2] if len(sys.argv) > 2 else "finance"
        backend = sys.argv[3] if len(sys.argv) > 3 else None
        rebuild_index(domain=domain, embed_backend=backend)
    elif cmd == "query":
        domain = sys.argv[2] if len(sys.argv) > 2 else "finance"
        q = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else "how to build an emergency fund"
        debug_query(q, domain=domain)
    elif cmd == "info":
        index_info(sys.argv[2] if len(sys.argv) > 2 else "finance")
    elif cmd == "test":
        run_test_suite(sys.argv[2] if len(sys.argv) > 2 else "finance")
    else:
        print("Usage:")
        print("  python -m core.rag.retriever rebuild [domain] [backend]")
        print("  python -m core.rag.retriever query [domain] <your query>")
        print("  python -m core.rag.retriever info [domain]")
        print("  python -m core.rag.retriever test [domain]")
