"""
SQLite-based analytics store for per-interaction metrics.
Records how each query was resolved (KB / web / general knowledge / none)
so the dashboard can show resolution rates, confidence, and escalations.
Additive-only: logging failures must never break the chat flow.
"""
import sqlite3
import json
import os
import logging
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger("analytics_store")

DEFAULT_DB_PATH = Path(os.getenv("ANALYTICS_DB_PATH", "data/memory/analytics.db"))


class AnalyticsStore:
    """Append-only log of chat interactions with aggregate queries."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    source TEXT NOT NULL,
                    kb_conf REAL,
                    num_citations INTEGER DEFAULT 0,
                    policy_flags TEXT,
                    query_chars INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_interactions_ts ON interactions(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_interactions_domain ON interactions(domain)")
            conn.commit()

    def log_interaction(
        self,
        domain: str,
        source: str,
        kb_conf: Optional[float] = None,
        num_citations: int = 0,
        policy_flags: Optional[List[str]] = None,
        query_chars: int = 0,
    ) -> None:
        """Record one chat interaction. Swallows errors — analytics must never break chat."""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """INSERT INTO interactions
                       (ts, domain, source, kb_conf, num_citations, policy_flags, query_chars)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        datetime.utcnow().isoformat(),
                        domain,
                        source,
                        kb_conf,
                        num_citations,
                        json.dumps(policy_flags or []),
                        query_chars,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"[ANALYTICS] Failed to log interaction: {e}")

    def summary(self, domain: Optional[str] = None) -> Dict[str, Any]:
        """Aggregate stats for the dashboard: totals, source breakdown, avg confidence."""
        where = "WHERE domain = ?" if domain else ""
        params = (domain,) if domain else ()
        with self._get_conn() as conn:
            total = conn.execute(f"SELECT COUNT(*) c FROM interactions {where}", params).fetchone()["c"]
            by_source = {
                row["source"]: row["c"]
                for row in conn.execute(
                    f"SELECT source, COUNT(*) c FROM interactions {where} GROUP BY source", params
                )
            }
            by_domain = {
                row["domain"]: row["c"]
                for row in conn.execute(
                    f"SELECT domain, COUNT(*) c FROM interactions {where} GROUP BY domain", params
                )
            }
            avg_conf_row = conn.execute(
                f"SELECT AVG(kb_conf) a FROM interactions {where}", params
            ).fetchone()
            cited = conn.execute(
                f"SELECT COUNT(*) c FROM interactions {where}{' AND' if where else 'WHERE'} num_citations > 0",
                params,
            ).fetchone()["c"]
            escalated = conn.execute(
                f"SELECT COUNT(*) c FROM interactions {where}{' AND' if where else 'WHERE'} policy_flags != '[]'",
                params,
            ).fetchone()["c"]

        grounded = by_source.get("kb", 0) + by_source.get("web", 0)
        return {
            "total_interactions": total,
            "by_source": by_source,
            "by_domain": by_domain,
            "grounded_rate": round(grounded / total, 4) if total else 0.0,
            "citation_rate": round(cited / total, 4) if total else 0.0,
            "escalation_rate": round(escalated / total, 4) if total else 0.0,
            "avg_kb_confidence": round(avg_conf_row["a"], 4) if avg_conf_row["a"] is not None else None,
        }

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Most recent interactions for the dashboard table."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM interactions ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [
                {
                    "ts": r["ts"],
                    "domain": r["domain"],
                    "source": r["source"],
                    "kb_conf": r["kb_conf"],
                    "num_citations": r["num_citations"],
                    "policy_flags": json.loads(r["policy_flags"]) if r["policy_flags"] else [],
                }
                for r in rows
            ]


_analytics_store: Optional[AnalyticsStore] = None
_analytics_lock = threading.Lock()


def get_analytics_store() -> AnalyticsStore:
    global _analytics_store
    if _analytics_store is None:
        with _analytics_lock:
            if _analytics_store is None:
                _analytics_store = AnalyticsStore()
    return _analytics_store
