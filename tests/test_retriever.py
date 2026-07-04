"""Unit tests for core/rag/retriever.py: embeddings, chunking, retrieval, isolation."""
import math

from core.rag.retriever import (
    CHUNK_SIZE,
    _hash_embed,
    _smart_chunk,
    kb_retrieve_with_confidence,
)


def test_hash_embed_is_deterministic_and_normalized():
    a = _hash_embed("build an emergency fund")
    b = _hash_embed("build an emergency fund")
    assert a == b
    norm = math.sqrt(sum(v * v for v in a))
    assert abs(norm - 1.0) < 1e-9
    assert len(a) == 512


def test_hash_embed_distinguishes_texts():
    a = _hash_embed("emergency fund savings account")
    b = _hash_embed("blood pressure medication dosage")
    cos = sum(x * y for x, y in zip(a, b))
    assert cos < 0.5


def test_smart_chunk_respects_size():
    text = "\n\n".join(f"## Section {i}\n\n" + ("word " * 120).strip() for i in range(5))
    chunks = _smart_chunk(text)
    assert len(chunks) > 1
    # Allow slack for overlap/boundary handling, but no runaway chunks
    assert all(len(c) <= CHUNK_SIZE * 2 for c in chunks)
    assert all(c.strip() for c in chunks)


def test_retrieve_finance_returns_finance_docs():
    hits, conf = kb_retrieve_with_confidence("how to build an emergency fund", k=3, domain="finance")
    assert hits, "expected finance hits"
    assert 0.0 < conf <= 0.98
    assert all("kb_finance" in h["url"] for h in hits)


def test_retrieve_healthcare_returns_healthcare_docs():
    hits, conf = kb_retrieve_with_confidence("when should I see a doctor about a fever", k=3, domain="healthcare")
    assert hits, "expected healthcare hits"
    assert 0.0 < conf <= 0.98
    assert all("kb_healthcare" in h["url"] for h in hits)


def test_domains_are_isolated():
    """A domain's results must only ever come from its own KB directory."""
    for domain, other in (("finance", "kb_healthcare"), ("healthcare", "kb_finance")):
        hits, _ = kb_retrieve_with_confidence("insurance coverage and costs", k=5, domain=domain)
        assert hits
        assert not any(other in h["url"] for h in hits), f"{domain} leaked from {other}"
