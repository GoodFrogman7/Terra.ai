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


def _load_text(path: Path) -> str:
    """Load text content from a file."""
    suf = path.suffix.lower()
    if suf in {".md", ".markdown", ".txt", ".csv", ".json"}:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
    if suf == ".pdf":
        return f"(PDF uploaded: {path.name})"
    return ""


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


def _load_index(index_path: Optional[str] = None, domain: str = "finance") -> dict:
    """Load index from disk, or build if not exists."""
    index_path = index_path or _get_index_path(domain)
    p = Path(index_path)
    if not p.exists():
        return build_index(domain=domain)
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


def _rerank(query: str, hits: List[Dict], enabled: bool) -> List[Dict]:
    """Rerank hits using keyword overlap boosting."""
    if not enabled or not hits:
        return hits
    q_tokens = set(_tokenize(query))
    
    def score(h):
        text = h.get("content", "")
        toks = set(_tokenize(text))
        overlap = len(q_tokens & toks)
        # Combine embedding score (70%) with keyword overlap (30%)
        return (h.get("score", 0.0) * 0.7) + (overlap * 0.03)
    
    return sorted(hits, key=score, reverse=True)


def kb_retrieve_with_confidence(query: str, k: int = 5, rerank: bool = False, domain: str = "finance") -> Tuple[List[Dict], float]:
    """
    Retrieve top-k KB chunks for a query.
    
    Args:
        query: Search query
        k: Number of results to return
        rerank: Whether to apply keyword reranking
        domain: Domain name (finance, healthcare)
    
    Returns:
        (list of hits, confidence score)
    """
    idx = _load_index(domain=domain)
    
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
    top_pairs = scored[:max(k, 8)]
    
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
    
    # Apply reranking
    hits = _rerank(query, hits, rerank)[:k]
    
    if not hits:
        return [], 0.0
    
    # Calculate confidence as average of top scores
    conf = sum(max(0.0, h["score"]) for h in hits) / len(hits)
    conf = min(0.98, max(0.0, conf))
    
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
    
    hits, conf = kb_retrieve_with_confidence(query, k=k, rerank=True)
    
    print(f"\nOverall confidence: {conf:.4f}")
    print(f"\nTop {len(hits)} results:")
    print("-" * 60)
    
    for i, h in enumerate(hits, 1):
        print(f"\n{i}. [{h['score']:.4f}] {h['title']}")
        snippet = h['content'][:200].replace('\n', ' ')
        print(f"   Snippet: {snippet}...")
    
    print(f"\n{'='*60}\n")


# CLI entry point for rebuild
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "rebuild":
        domain = sys.argv[2] if len(sys.argv) > 2 else "finance"
        backend = sys.argv[3] if len(sys.argv) > 3 else None
        rebuild_index(domain=domain, embed_backend=backend)
    elif len(sys.argv) > 1 and sys.argv[1] == "query":
        domain = sys.argv[2] if len(sys.argv) > 2 else "finance"
        q = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else "how to save battery"
        debug_query(q, domain=domain)
    else:
        print("Usage:")
        print("  python -m core.rag.retriever rebuild [domain] [backend]")
        print("  python -m core.rag.retriever query [domain] <your query>")
