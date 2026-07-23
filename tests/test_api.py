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


@pytest.fixture()
def invite_gated_auth_mode(monkeypatch: pytest.MonkeyPatch):
    """Auth mode with an invite code required. example.invalid guarantees any
    accidental Supabase call fails fast instead of hitting the network."""
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "fake")
    monkeypatch.setenv("DEMO_INVITE_CODE", "sekrit")


def test_signup_rejects_wrong_invite_code(invite_gated_auth_mode):
    client = TestClient(app)
    r = client.post("/auth/signup", json={"email": "a@b.co", "password": "hunter22", "invite_code": "wrong"})
    assert r.status_code == 403
    assert r.json()["detail"] == "Invalid or missing invite code"


def test_signup_rejects_missing_invite_code(invite_gated_auth_mode):
    client = TestClient(app)
    r = client.post("/auth/signup", json={"email": "a@b.co", "password": "hunter22"})
    assert r.status_code == 403
    assert r.json()["detail"] == "Invalid or missing invite code"


def test_signup_local_mode_ignores_invite_code(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEMO_INVITE_CODE", "sekrit")
    r = client.post("/auth/signup", json={"email": "a@b.co", "password": "hunter22"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "local_mode": True}


def test_signup_auth_mode_without_invite_gate(monkeypatch: pytest.MonkeyPatch):
    """DEMO_INVITE_CODE unset: signup proceeds to sign_up (mocked) even without invite_code."""
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "fake")
    monkeypatch.delenv("DEMO_INVITE_CODE", raising=False)
    import apps.api.main as main_mod
    monkeypatch.setattr(main_mod, "sign_up", lambda email, password: {"id": "x"})
    client = TestClient(app)
    r = client.post("/auth/signup", json={"email": "a@b.co", "password": "hunter22"})
    assert r.status_code == 200
    assert r.json() == {"id": "x"}


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


def test_upload_rejects_unreadable_pdf(client: TestClient):
    body = client.post(
        "/upload", files={"file": ("scanned_policy.pdf", b"not a valid PDF")}, data={"domain": "finance"}
    ).json()
    assert not body["ok"]
    assert "extractable text" in body["msg"]


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


def test_chat_overrides_do_not_leak_into_environ(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """embed_backend/kb_threshold are request-scoped state, never process env."""
    import os
    monkeypatch.delenv("EMBED_BACKEND", raising=False)
    monkeypatch.delenv("KB_CONFIDENCE_THRESHOLD", raising=False)
    r = client.post(
        "/chat",
        json={
            "message": "how do I build an emergency fund",
            "domain": "finance",
            "web_enabled": False,
            "kb_threshold": 0.31,
            "embed_backend": "ollama:nomic-embed-text",
            "summarizer_model": "none",
        },
    )
    assert r.status_code == 200
    assert "EMBED_BACKEND" not in os.environ
    assert "KB_CONFIDENCE_THRESHOLD" not in os.environ


def _sse_events(text: str) -> list:
    return [json.loads(l[5:]) for l in text.splitlines() if l.startswith("data:")]


def test_chat_stream_kb_answer_contract(client: TestClient):
    r = client.get(
        "/chat_stream",
        params={
            "message": "how do I build an emergency fund",
            "domain": "finance",
            "web_enabled": "false",
            "kb_threshold": "0.05",
            "embed_backend": "hash",
        },
    )
    events = _sse_events(r.text)
    done = events[-1]
    assert done["done"] and done["source"] == "kb" and done["citations"]
    answer = "".join(e.get("delta", "") for e in events[:-1])
    assert answer.strip()


def test_chat_stream_rejects_invalid_embed_backend(client: TestClient):
    """Invalid backend must produce the SSE error envelope, not mutate the env."""
    import os
    r = client.get("/chat_stream", params={"message": "hi", "domain": "finance", "embed_backend": "rm -rf /"})
    events = _sse_events(r.text)
    assert "ValueError" in events[0]["delta"]
    assert "api_error" in events[-1]["policy_flags"]
    assert os.environ.get("EMBED_BACKEND") != "rm -rf /"


def test_rate_limit_429_after_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from apps.api.rate_limit import reset_rate_limiter
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    reset_rate_limiter()
    payload = {"message": "hi", "domain": "finance", "web_enabled": False,
               "kb_threshold": 0.99, "summarizer_model": "none"}
    for _ in range(3):
        assert client.post("/chat", json=payload).status_code == 200
    r = client.post("/chat", json=payload)
    assert r.status_code == 429
    assert r.json()["detail"] == "Rate limit exceeded, try again shortly"
    reset_rate_limiter()


def test_rate_limit_disabled_when_zero(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from apps.api.rate_limit import reset_rate_limiter
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "0")
    reset_rate_limiter()
    payload = {"message": "hi", "domain": "finance", "web_enabled": False,
               "kb_threshold": 0.99, "summarizer_model": "none"}
    for _ in range(10):
        assert client.post("/chat", json=payload).status_code == 200


def test_rate_limit_covers_auth_endpoints(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from apps.api.rate_limit import reset_rate_limiter
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    reset_rate_limiter()
    creds = {"email": "a@b.co", "password": "hunter22"}
    assert client.post("/auth/login", json=creds).status_code == 200
    assert client.post("/auth/login", json=creds).status_code == 200
    assert client.post("/auth/login", json=creds).status_code == 429
    reset_rate_limiter()


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


def test_chat_uses_safe_default_threshold_and_web_off(client: TestClient):
    body = client.post(
        "/chat",
        json={"message": "how do I build an emergency fund", "domain": "finance", "summarizer_model": "none"},
    ).json()
    assert body["source"] == "kb"
    assert body["citations"]


def test_chat_defaults_to_strict_source_backed_answers(client: TestClient):
    body = client.post(
        "/chat",
        json={"message": "What is the institution's wire transfer exception procedure?", "domain": "finance"},
    ).json()
    assert body["source"] == "none"
    assert body["citations"] == []
    assert body["answer"] == "I cannot verify that in the approved sources."
