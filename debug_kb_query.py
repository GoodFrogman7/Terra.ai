#!/usr/bin/env python3
"""
Debug utility for testing KB retrieval.

Usage:
    python debug_kb_query.py "your query here"
    python debug_kb_query.py --rebuild [backend]
    python debug_kb_query.py --info

Examples:
    python debug_kb_query.py "how to build an emergency fund"
    python debug_kb_query.py "managing chronic conditions"
    python debug_kb_query.py "retirement planning basics"
    python debug_kb_query.py --rebuild ollama:nomic-embed-text
    python debug_kb_query.py --rebuild hash
"""

import os
import sys

# Set environment variables before importing
os.environ.setdefault("OLLAMA_HOST", "http://localhost:11434")
os.environ.setdefault("KB_DIR", "data/kb")
os.environ.setdefault("INDEX_DIR", "data/index")

from core.rag.retriever import (
    kb_retrieve_with_confidence,
    rebuild_index,
    clear_index,
    _load_index,
    INDEX_PATH,
    KB_DIR
)


def show_info():
    """Show current index information."""
    print("\n" + "=" * 60)
    print("KB INDEX INFORMATION")
    print("=" * 60)
    
    try:
        idx = _load_index(INDEX_PATH)
        meta = idx.get("meta", {})
        
        print(f"Index path: {INDEX_PATH}")
        print(f"Embedding backend: {meta.get('embed_backend', 'unknown')}")
        print(f"Vector dimension: {meta.get('dim', 'unknown')}")
        print(f"Number of documents: {meta.get('num_docs', 'unknown')}")
        print(f"Number of chunks: {meta.get('num_chunks', len(idx.get('entries', [])))}")
        print(f"Chunk size: {meta.get('chunk_size', 'unknown')}")
        print(f"Chunk overlap: {meta.get('chunk_overlap', 'unknown')}")
        
        # List source files
        files = set(e.get("title", "") for e in idx.get("entries", []))
        print(f"\nSource files ({len(files)}):")
        for f in sorted(files):
            count = sum(1 for e in idx.get("entries", []) if e.get("title") == f)
            print(f"  - {f}: {count} chunks")
            
    except Exception as e:
        print(f"Error loading index: {e}")
        print("Run: python debug_kb_query.py --rebuild")
    
    print("=" * 60 + "\n")


def test_query(query: str, k: int = 5):
    """Run a test query and show detailed results."""
    print("\n" + "=" * 60)
    print(f"QUERY: {query}")
    print("=" * 60)
    
    # Get results
    hits, confidence = kb_retrieve_with_confidence(query, k=k, rerank=True)
    
    # Load index info
    try:
        idx = _load_index(INDEX_PATH)
        meta = idx.get("meta", {})
        print(f"Using backend: {meta.get('embed_backend', 'unknown')}")
    except:
        pass
    
    print(f"Confidence score: {confidence:.4f}")
    print(f"Results: {len(hits)}")
    print("-" * 60)
    
    if not hits:
        print("NO RESULTS FOUND!")
        print("Try running: python debug_kb_query.py --rebuild ollama:nomic-embed-text")
    else:
        for i, hit in enumerate(hits, 1):
            score = hit.get("score", 0)
            title = hit.get("title", "Unknown")
            content = hit.get("content", "")[:250].replace("\n", " ").strip()
            
            # Color code by score
            if score >= 0.7:
                status = "EXCELLENT"
            elif score >= 0.5:
                status = "GOOD"
            elif score >= 0.3:
                status = "FAIR"
            else:
                status = "LOW"
            
            print(f"\n{i}. Score: {score:.4f} [{status}]")
            print(f"   File: {title}")
            print(f"   Content: {content}...")
    
    print("\n" + "-" * 60)
    print("THRESHOLD RECOMMENDATIONS:")
    if confidence >= 0.5:
        print("  Current confidence is GOOD. Threshold 0.4-0.5 recommended.")
    elif confidence >= 0.3:
        print("  Current confidence is FAIR. Threshold 0.25-0.35 recommended.")
    else:
        print("  Current confidence is LOW. Try:")
        print("  1. Rebuild index: python debug_kb_query.py --rebuild ollama:nomic-embed-text")
        print("  2. Use lower threshold: 0.1-0.2")
        print("  3. Check if KB has relevant content for this query")
    
    print("=" * 60 + "\n")
    
    return hits, confidence


def do_rebuild(backend: str = None):
    """Rebuild the KB index."""
    backend = backend or os.getenv("EMBED_BACKEND", "ollama:nomic-embed-text")
    
    print("\n" + "=" * 60)
    print("REBUILDING KB INDEX")
    print("=" * 60)
    print(f"KB Directory: {KB_DIR}")
    print(f"Embedding Backend: {backend}")
    print("-" * 60)
    
    # Set the backend
    os.environ["EMBED_BACKEND"] = backend
    
    # Rebuild
    result = rebuild_index(embed_backend=backend)
    
    print("-" * 60)
    meta = result.get("meta", {})
    print(f"SUCCESS!")
    print(f"  Documents: {meta.get('num_docs', 0)}")
    print(f"  Chunks: {meta.get('num_chunks', 0)}")
    print(f"  Backend: {meta.get('embed_backend', 'unknown')}")
    print("=" * 60 + "\n")
    
    return result


def run_test_suite():
    """Run a suite of test queries."""
    test_queries = [
        "how to build an emergency fund",
        "credit card debt payoff strategies",
        "retirement planning basics",
        "managing chronic conditions",
        "when to see a doctor",
        "preventive care checklist",
        "budgeting for beginners",
    ]
    
    print("\n" + "=" * 60)
    print("RUNNING TEST SUITE")
    print("=" * 60)
    
    results = []
    for q in test_queries:
        hits, conf = kb_retrieve_with_confidence(q, k=3, rerank=True)
        top_score = hits[0]["score"] if hits else 0
        results.append((q, conf, top_score, len(hits)))
        print(f"  [{conf:.3f}] {q}")
    
    avg_conf = sum(r[1] for r in results) / len(results)
    print("-" * 60)
    print(f"Average confidence: {avg_conf:.4f}")
    
    if avg_conf >= 0.4:
        print("KB retrieval is working well!")
        print(f"Recommended threshold: {max(0.3, avg_conf - 0.15):.2f} - {avg_conf:.2f}")
    else:
        print("KB retrieval needs improvement.")
        print("Try: python debug_kb_query.py --rebuild ollama:nomic-embed-text")
    
    print("=" * 60 + "\n")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    
    arg = sys.argv[1]
    
    if arg == "--info":
        show_info()
    elif arg == "--rebuild":
        backend = sys.argv[2] if len(sys.argv) > 2 else None
        do_rebuild(backend)
    elif arg == "--test":
        run_test_suite()
    elif arg.startswith("--"):
        print(f"Unknown option: {arg}")
        print(__doc__)
    else:
        query = " ".join(sys.argv[1:])
        test_query(query)


if __name__ == "__main__":
    main()

