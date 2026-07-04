"""
In-memory sliding-window rate limiting for the API.

Keyed by the authenticated user_id when one is available, otherwise by the
client IP. The limit comes from RATE_LIMIT_PER_MINUTE, read dynamically on
every request: unset/blank -> default 60; 0 (or an unparseable value) disables
limiting entirely.

Purely in-process (like the auth token cache in core/auth/supabase_auth.py):
suitable for a single-instance deployment. Memory stays bounded by pruning
expired timestamps on every hit and opportunistically evicting idle keys once
~10k keys are tracked.
"""
import os
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Optional

from fastapi import Depends, HTTPException, Request

from core.auth.supabase_auth import LOCAL_USER_ID, get_current_user

_WINDOW_SECONDS = 60.0
_DEFAULT_LIMIT = 60
_MAX_TRACKED_KEYS = 10_000

_hits: Dict[str, Deque[float]] = {}  # key -> monotonic timestamps within the window
_lock = threading.Lock()


def _limit_per_minute() -> int:
    """Effective requests-per-minute limit; 0 means limiting is disabled."""
    raw = os.getenv("RATE_LIMIT_PER_MINUTE")
    if raw is None or not raw.strip():
        return _DEFAULT_LIMIT
    try:
        limit = int(raw.strip())
    except ValueError:
        return 0
    return limit if limit > 0 else 0


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def check_rate_limit(key: str) -> None:
    """Record a hit for `key`; raise 429 when the sliding window is full."""
    limit = _limit_per_minute()
    if limit <= 0:
        return
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS
    with _lock:
        if key not in _hits and len(_hits) >= _MAX_TRACKED_KEYS:
            # Opportunistic cleanup so the map can't grow unboundedly
            for stale in [k for k, dq in _hits.items() if not dq or dq[-1] <= cutoff]:
                del _hits[stale]
            if len(_hits) >= _MAX_TRACKED_KEYS:
                _hits.clear()
        window = _hits.setdefault(key, deque())
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded, try again shortly")
        window.append(now)


async def rate_limit_by_ip(request: Request) -> None:
    """Dependency for unauthenticated routes (/auth/*): keys on client IP."""
    check_rate_limit(_client_ip(request))


async def rate_limit_by_user(
    request: Request, user: Dict[str, Any] = Depends(get_current_user)
) -> None:
    """Dependency for authenticated routes: keys on user_id, else client IP.

    Depends on get_current_user so auth resolves first (FastAPI caches the
    sub-dependency, so routes that also declare it don't verify twice).
    """
    user_id: Optional[str] = user.get("user_id")
    key = user_id if user_id and user_id != LOCAL_USER_ID else _client_ip(request)
    check_rate_limit(key)


def reset_rate_limiter() -> None:
    """Clear all tracked windows (test isolation helper)."""
    with _lock:
        _hits.clear()
