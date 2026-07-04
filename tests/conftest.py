"""Shared test setup: repo root on sys.path, forced local (no-auth) mode."""
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Tests always run from the repo root so relative paths (config/domains.json,
# data/kb_*) resolve the same way they do for uvicorn.
os.chdir(REPO_ROOT)


@pytest.fixture()
def local_mode(monkeypatch: pytest.MonkeyPatch):
    """Force single-user local mode even when a developer .env sets Supabase vars.

    auth_enabled() reads the env dynamically, so deleting the vars per-test is
    enough — no reimport needed.
    """
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
