"""
Supabase Auth integration.

Auth is optional by configuration: when SUPABASE_URL / SUPABASE_ANON_KEY are
unset, the app runs in single-user "local" mode (every request maps to
user_id "local"). When set, API routes require a Supabase JWT and all
chat/memory data is scoped to the authenticated user.

Token verification calls Supabase's /auth/v1/user endpoint (no JWT secret
needed locally) with a short in-memory TTL cache so repeated requests from
the same session don't hammer the auth server.
"""
import os
import time
import threading
from typing import Optional, Dict, Any

import requests
from fastapi import Header, HTTPException

LOCAL_USER_ID = "local"
_TOKEN_CACHE_TTL_SECONDS = 60.0

_token_cache: Dict[str, tuple] = {}  # token -> (expires_at_monotonic, user_dict)
_cache_lock = threading.Lock()


def _supabase_url() -> str:
    return os.getenv("SUPABASE_URL", "").strip().rstrip("/")


def _supabase_anon_key() -> str:
    return os.getenv("SUPABASE_ANON_KEY", "").strip()


def auth_enabled() -> bool:
    """Auth is on only when both Supabase settings are present."""
    return bool(_supabase_url() and _supabase_anon_key())


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Validate a Supabase access token. Returns {user_id, email} or None."""
    now = time.monotonic()
    with _cache_lock:
        cached = _token_cache.get(token)
        if cached and cached[0] > now:
            return cached[1]

    try:
        r = requests.get(
            f"{_supabase_url()}/auth/v1/user",
            headers={"apikey": _supabase_anon_key(), "Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if not r.ok:
            return None
        data = r.json()
        user = {"user_id": data.get("id", ""), "email": data.get("email", "")}
        if not user["user_id"]:
            return None
    except Exception:
        return None

    with _cache_lock:
        # Opportunistic cleanup so the cache can't grow unboundedly
        if len(_token_cache) > 1000:
            _token_cache.clear()
        _token_cache[token] = (now + _TOKEN_CACHE_TTL_SECONDS, user)
    return user


def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """FastAPI dependency: resolves the requesting user.

    Local mode (no Supabase config): always returns the shared local user.
    Auth mode: requires a valid `Authorization: Bearer <jwt>` header.
    """
    if not auth_enabled():
        return {"user_id": LOCAL_USER_ID, "email": ""}

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    user = verify_token(authorization.split(" ", 1)[1].strip())
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def sign_up(email: str, password: str) -> Dict[str, Any]:
    """Proxy signup to Supabase. Returns the raw auth response."""
    r = requests.post(
        f"{_supabase_url()}/auth/v1/signup",
        headers={"apikey": _supabase_anon_key(), "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=15,
    )
    body = r.json() if r.content else {}
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=body.get("msg") or body.get("error_description") or "Signup failed")
    return body


def sign_in(email: str, password: str) -> Dict[str, Any]:
    """Proxy password login to Supabase. Returns {access_token, ...}."""
    r = requests.post(
        f"{_supabase_url()}/auth/v1/token?grant_type=password",
        headers={"apikey": _supabase_anon_key(), "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=15,
    )
    body = r.json() if r.content else {}
    if not r.ok:
        raise HTTPException(status_code=r.status_code, detail=body.get("msg") or body.get("error_description") or "Login failed")
    return body
