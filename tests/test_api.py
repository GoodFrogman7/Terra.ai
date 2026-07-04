"""API tests via FastAPI TestClient, run in forced local (no-auth) mode.

The domain-upload test writes into the real data/kb_finance dir and rebuilds
the real finance index; its fixture always restores the committed state
(hash embeddings are deterministic, so a rebuild reproduces it exactly).
"""
import json
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from core.rag.retriever import build_index, kb_retrieve_with_confidence


@pytest.fixture()
def client(local_mode) -> TestClient:
    return TestClient(app)


@pytest.fixture()
def finance_kb_restored() -> Iterator[list]:
    """Collects uploaded file paths; removes them and rebuilds the finance index after."""
    uploaded: list = []
    try:
        yield uploaded
    finally:
        for p in uploaded:
            Path(p).unlink(missing_ok=True)
        build_index(domain="finance")


def test_healthz(client: TestClient):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["ok"]


def test_auth_status_local_mode(client: TestClient):
    assert client.get("/auth/status").json() == {"auth_enabled": False}


def test_config_lists_domains_and_allowlists(client: TestClient):
    cfg = client.get("/config").json()
    assert set(cfg["domains"]) == {"finance", "healthcare"}
    assert "none" in cfg["summarizer_models"]
    assert "hash" in cfg["embed_backends"]


def test_upload_rejects_bad_extension(client: TestClient):
    r = client.post("/upload", files={"file": ("evil.exe", b"MZ")})
    assert r.status_code == 200 and not r.json()["ok"]


def test_upload_rejects_unknown_domain(client: TestClient):
    r = client.post("/upload", files={"file": ("x.md", b"# x")}, data={"domain": "crypto"})
    body = r.json()
    assert not body["ok"] and "Unknown domain" in body["msg"]


def test_domain_upload_indexes_and_isolates(client: TestClient, finance_kb_restored: list):
    baseline = client.post("/reindex", params={"domain": "finance"}).json()["indexed_docs"]

    md = b"# Wire Transfer Limits\n\nDaily wire transfer limits for retail accounts are $25,000.\n"
    body = client.post(
        "/upload", files={"file": ("wire_transfer_limits.md", md)}, data={"domain": "finance"}
    ).json()
    finance_kb_restored.append(body.get("path", ""))
    assert body["ok"] and body["domain"] == "finance"
    assert "kb_finance" in body["path"]
    assert body["indexed_docs"] > baseline

    hits, _ = kb_retrieve_with_confidence("daily wire transfer limit", k=3, domain="finance")
    assert any("wire_transfer" in h["title"] for h in hits)
    other, _ = kb_retrieve_with_confidence("daily wire transfer limit", k=3, domain="healthcare")
    assert not any("wire_transfer" in h["title"] for h in other), "cross-domain leak"


def test_domain_reindex(client: TestClient):
    body = client.post("/reindex", params={"domain": "healthcare"}).json()
    assert body["ok"] and body["domain"] == "healthcare" and body["indexed_docs"] > 0


def test_chat_kb_answer_contract(client: TestClient):
    body = client.post(
        "/chat",
        json={
            "message": "how do I build an emergency fund",
            "domain": "finance",
            "web_enabled": False,
            "kb_threshold": 0.05,
            "summarizer_model": "none",
        },
    ).json()
    assert body["source"] == "kb"
    assert body["citations"]
    assert body["answer"].strip()
    assert isinstance(body["policy_flags"], list)
