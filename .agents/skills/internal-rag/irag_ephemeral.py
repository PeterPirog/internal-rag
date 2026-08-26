#!/usr/bin/env python3
"""irag_ephemeral.py — ephemeral observations layer for MCP Light Memory.

A separate, bounded, TTL-based storage for raw tool outputs (console, terminal,
builds, lints, tests) that are NOT durable Markdown memory. Observations flow
through a lifecycle:

  raw tool output -> ephemeral observation -> distillation -> admission -> durable conclusion -> raw observation deletion

Storage:
  - SQLite table in .index.sqlite3 (or a separate .ephemeral.db if no index)
  - Bounded by max_records and max_bytes
  - TTL-based expiry (default 30 minutes)
  - Cleaned on session end or TTL expiry
  - Never stores secrets, credentials, or production data
  - Not indexed for retrieval (does not leak into active durable memory)

Stdlib-only (Python 3.8+). No external dependencies.
"""
from __future__ import annotations
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Defaults (configurable via .irag.yml -> ephemeral.*)
DEFAULT_TTL_SECONDS = 30 * 60        # 30 minutes
DEFAULT_MAX_RECORDS = 200
DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 2 MB total
DEFAULT_MAX_RECORD_BYTES = 64 * 1024  # 64 KB per observation

EPHEMERAL_TABLE = "ephemeral_observations"


def _ephemeral_db_path(rag_dir: Path) -> Path:
    """Return the path for the ephemeral SQLite database."""
    # Use the existing .index.sqlite3 if present, else a separate .ephemeral.db
    idx = rag_dir / ".index.sqlite3"
    if idx.exists():
        return idx
    return rag_dir / ".ephemeral.db"


def _open_ephemeral(rag_dir: Path) -> Optional[sqlite3.Connection]:
    """Open a SQLite connection for ephemeral observations. Returns None on failure."""
    try:
        db_path = _ephemeral_db_path(rag_dir)
        rag_dir.mkdir(exist_ok=True)
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {EPHEMERAL_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                source TEXT NOT NULL,
                command TEXT,
                exit_code INTEGER,
                content TEXT NOT NULL,
                content_hash TEXT,
                content_bytes INTEGER NOT NULL DEFAULT 0,
                promoted INTEGER NOT NULL DEFAULT 0,
                promoted_to TEXT,
                distilled TEXT,
                metadata TEXT
            )
        """)
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{EPHEMERAL_TABLE}_expires "
                     f"ON {EPHEMERAL_TABLE}(expires_at)")
        conn.commit()
        return conn
    except Exception:
        return None


def add_observation(rag_dir: Path,
                    source: str,
                    content: str,
                    command: Optional[str] = None,
                    exit_code: Optional[int] = None,
                    ttl_seconds: int = DEFAULT_TTL_SECONDS,
                    max_record_bytes: int = DEFAULT_MAX_RECORD_BYTES,
                    max_records: int = DEFAULT_MAX_RECORDS,
                    max_bytes: int = DEFAULT_MAX_BYTES,
                    metadata: Optional[Dict[str, Any]] = None,
                    ) -> Optional[int]:
    """Add an ephemeral observation. Returns the observation id, or None on failure.

    Truncates content to max_record_bytes. Enforces max_records and max_bytes
    by evicting the oldest observations.
    """
    # Truncate content
    content_bytes = len(content.encode("utf-8"))
    if content_bytes > max_record_bytes:
        content = content[:max_record_bytes // 2] + "\n... [truncated] ...\n"
        content_bytes = len(content.encode("utf-8"))

    # Never store secrets — basic check
    content_lower = content.lower()
    for pat in ("password=", "api_key=", "secret=", "token=", "aws_secret_access_key"):
        if pat in content_lower:
            content = f"[REDACTED: observation contained potential secret '{pat}...']"
            content_bytes = len(content.encode("utf-8"))
            break

    conn = _open_ephemeral(rag_dir)
    if conn is None:
        return None
    try:
        now_t = time.time()
        expires_at = now_t + ttl_seconds
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        meta_json = json.dumps(metadata) if metadata else None
        cur = conn.execute(
            f"INSERT INTO {EPHEMERAL_TABLE} "
            "(created_at, expires_at, source, command, exit_code, content, "
            "content_hash, content_bytes, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now_t, expires_at, source, command, exit_code, content,
             content_hash, content_bytes, meta_json))
        obs_id = cur.lastrowid

        # Enforce max_records: evict oldest
        count = conn.execute(
            f"SELECT COUNT(*) FROM {EPHEMERAL_TABLE}").fetchone()[0]
        if count > max_records:
            conn.execute(
                f"DELETE FROM {EPHEMERAL_TABLE} WHERE id IN "
                f"(SELECT id FROM {EPHEMERAL_TABLE} ORDER BY created_at ASC LIMIT ?)",
                (count - max_records,))

        # Enforce max_bytes: evict oldest
        total = conn.execute(
            f"SELECT COALESCE(SUM(content_bytes), 0) FROM {EPHEMERAL_TABLE}"
        ).fetchone()[0]
        if total > max_bytes:
            conn.execute(
                f"DELETE FROM {EPHEMERAL_TABLE} WHERE id IN "
                f"(SELECT id FROM {EPHEMERAL_TABLE} ORDER BY created_at ASC LIMIT 50)")

        # Clean expired
        conn.execute(
            f"DELETE FROM {EPHEMERAL_TABLE} WHERE expires_at < ?",
            (now_t,))

        conn.commit()
        return obs_id
    except Exception:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_observation(rag_dir: Path, obs_id: int) -> Optional[Dict[str, Any]]:
    """Get a single observation by id. Returns None if not found or expired."""
    conn = _open_ephemeral(rag_dir)
    if conn is None:
        return None
    try:
        now_t = time.time()
        row = conn.execute(
            f"SELECT * FROM {EPHEMERAL_TABLE} WHERE id = ? AND expires_at > ?",
            (obs_id, now_t)).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)
    except Exception:
        return None
    finally:
        conn.close()


def list_observations(rag_dir: Path, source: Optional[str] = None,
                      limit: int = 20) -> List[Dict[str, Any]]:
    """List recent non-expired observations, optionally filtered by source."""
    conn = _open_ephemeral(rag_dir)
    if conn is None:
        return []
    try:
        now_t = time.time()
        if source:
            rows = conn.execute(
                f"SELECT * FROM {EPHEMERAL_TABLE} "
                f"WHERE expires_at > ? AND source = ? "
                f"ORDER BY created_at DESC LIMIT ?",
                (now_t, source, limit)).fetchall()
        else:
            rows = conn.execute(
                f"SELECT * FROM {EPHEMERAL_TABLE} "
                f"WHERE expires_at > ? "
                f"ORDER BY created_at DESC LIMIT ?",
                (now_t, limit)).fetchall()
        return [_row_to_dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def delete_observation(rag_dir: Path, obs_id: int) -> bool:
    """Delete a single observation (e.g. after promotion to durable memory)."""
    conn = _open_ephemeral(rag_dir)
    if conn is None:
        return False
    try:
        cur = conn.execute(
            f"DELETE FROM {EPHEMERAL_TABLE} WHERE id = ?", (obs_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def mark_promoted(rag_dir: Path, obs_id: int, promoted_to: str,
                  distilled: Optional[str] = None) -> bool:
    """Mark an observation as promoted to durable memory (and optionally delete it)."""
    conn = _open_ephemeral(rag_dir)
    if conn is None:
        return False
    try:
        conn.execute(
            f"UPDATE {EPHEMERAL_TABLE} SET promoted = 1, promoted_to = ?, distilled = ? "
            f"WHERE id = ?",
            (promoted_to, distilled, obs_id))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def cleanup_expired(rag_dir: Path) -> int:
    """Delete all expired observations. Returns the count deleted."""
    conn = _open_ephemeral(rag_dir)
    if conn is None:
        return 0
    try:
        now_t = time.time()
        cur = conn.execute(
            f"DELETE FROM {EPHEMERAL_TABLE} WHERE expires_at < ?", (now_t,))
        conn.commit()
        return cur.rowcount
    except Exception:
        conn.rollback()
        return 0
    finally:
        conn.close()


def clear_all(rag_dir: Path) -> int:
    """Delete ALL observations (e.g. on session end). Returns the count deleted."""
    conn = _open_ephemeral(rag_dir)
    if conn is None:
        return 0
    try:
        cur = conn.execute(f"DELETE FROM {EPHEMERAL_TABLE}")
        conn.commit()
        return cur.rowcount
    except Exception:
        conn.rollback()
        return 0
    finally:
        conn.close()


def ephemeral_stats(rag_dir: Path) -> Dict[str, Any]:
    """Return stats about the ephemeral store."""
    conn = _open_ephemeral(rag_dir)
    if conn is None:
        return {"available": False, "count": 0, "total_bytes": 0,
                "expired": 0, "promoted": 0}
    try:
        now_t = time.time()
        count = conn.execute(
            f"SELECT COUNT(*) FROM {EPHEMERAL_TABLE}").fetchone()[0]
        total_bytes = conn.execute(
            f"SELECT COALESCE(SUM(content_bytes), 0) FROM {EPHEMERAL_TABLE}"
        ).fetchone()[0]
        expired = conn.execute(
            f"SELECT COUNT(*) FROM {EPHEMERAL_TABLE} WHERE expires_at < ?",
            (now_t,)).fetchone()[0]
        promoted = conn.execute(
            f"SELECT COUNT(*) FROM {EPHEMERAL_TABLE} WHERE promoted = 1"
        ).fetchone()[0]
        return {"available": True, "count": count, "total_bytes": total_bytes,
                "expired": expired, "promoted": promoted}
    except Exception:
        return {"available": False, "count": 0, "total_bytes": 0,
                "expired": 0, "promoted": 0}
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert a database row to a dict."""
    cols = ["id", "created_at", "expires_at", "source", "command", "exit_code",
            "content", "content_hash", "content_bytes", "promoted",
            "promoted_to", "distilled", "metadata"]
    d = {col: row[i] for i, col in enumerate(cols)}
    if d.get("metadata"):
        try:
            d["metadata"] = json.loads(d["metadata"])
        except Exception:
            pass
    return d