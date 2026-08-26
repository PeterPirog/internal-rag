#!/usr/bin/env python3
"""irag_ephemeral.py — ephemeral observations layer for MCP Light Memory.

A separate, bounded, TTL-based storage for raw tool outputs (console, terminal,
builds, lints, tests) that are NOT durable Markdown memory. Observations flow
through a lifecycle:

  raw tool output -> ephemeral observation -> distillation -> admission -> durable conclusion -> raw observation deletion

Storage:
  - SQLite table in a STABLE, dedicated database: INTERNAL_RAG/.ephemeral.db.
    Raw observations are NOT part of the rebuildable retrieval index, so they
    have their own DB (never the .index.sqlite3 retrieval index). This makes
    the observation identity stable across `index --rebuild`.
  - Bounded by max_records and max_bytes (hard cap — evict oldest until
    SUM(content_bytes) <= max_bytes after every insert).
  - TTL-based expiry (default 30 minutes).
  - Cleaned on session end or TTL expiry.
  - Never stores secrets, credentials, or production data — content, command,
    and metadata are scanned/redacted BEFORE SQLite storage using the same
    secret patterns as durable `remember()`.
  - Not indexed for retrieval (does not leak into active durable memory).

Stdlib-only (Python 3.8+). No external dependencies.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
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

# Stable, dedicated DB path for ephemeral observations. This is NOT the
# retrieval index (.index.sqlite3) — raw observations are never rebuildable,
# so they live in their own database to keep identity stable across
# `index --rebuild`.
EPHEMERAL_DB_NAME = ".ephemeral.db"
# Legacy DB: some short-lived v1.8.0 builds stored observations in the
# retrieval index. We migrate the table over (best-effort, no heavy framework)
# and stop writing to it.
LEGACY_INDEX_DB_NAME = ".index.sqlite3"


# Secret detection — same level as durable remember(). Applied to content,
# command, and metadata BEFORE SQLite storage so secrets never hit the DB.
_SECRET_PATTERNS: List[re.Pattern] = [
    re.compile(r"(?i)(?:password|passwd|pwd)\s*[:=]\s*\S{4,}"),
    re.compile(r"(?i)(?:api[_-]?key|apikey)\s*[:=]\s*\S{8,}"),
    re.compile(r"(?i)(?:secret|token)\s*[:=]\s*\S{8,}"),
    re.compile(r"(?i)(?:AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-._~+]{20,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}"),
    re.compile(r"sk-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*"),
    re.compile(r"(?i)xox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
]


def _scan_secrets(text: str) -> List[str]:
    """Return list of detected secret pattern descriptions (same level as
    durable remember())."""
    if not text:
        return []
    found: List[str] = []
    for pat in _SECRET_PATTERNS:
        if pat.search(text):
            found.append(pat.pattern[:60])
    return found


def _redact(text: Optional[str], field_name: str) -> Optional[str]:
    """If `text` contains a secret pattern, replace it with a redaction
    marker. Returns the (possibly redacted) text, or None if input is None."""
    if text is None:
        return None
    if _scan_secrets(text):
        return f"[REDACTED: {field_name} contained a potential secret]"
    return text


def _ephemeral_db_path(rag_dir: Path) -> Path:
    """Return the STABLE path for the ephemeral SQLite database.

    Always INTERNAL_RAG/.ephemeral.db — never the retrieval index. This keeps
    observation identity stable across `index --rebuild`.
    """
    return rag_dir / EPHEMERAL_DB_NAME


def _legacy_index_has_table(rag_dir: Path) -> bool:
    """Check if the legacy .index.sqlite3 contains an ephemeral_observations
    table (short-lived v1.8.0 builds). Best-effort, no migration framework."""
    idx = rag_dir / LEGACY_INDEX_DB_NAME
    if not idx.exists():
        return False
    try:
        conn = sqlite3.connect(str(idx), timeout=5)
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (EPHEMERAL_TABLE,)).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return False


def _migrate_legacy_table(rag_dir: Path, dest_conn: sqlite3.Connection) -> int:
    """Best-effort copy of legacy ephemeral rows from .index.sqlite3 into the
    dedicated .ephemeral.db. Returns the number of rows migrated (0 if none or
    failure). The legacy table is left in place (not dropped) — harmless once
    we stop reading it."""
    idx = rag_dir / LEGACY_INDEX_DB_NAME
    if not idx.exists() or not _legacy_index_has_table(rag_dir):
        return 0
    try:
        src = sqlite3.connect(str(idx), timeout=5)
        try:
            rows = src.execute(
                f"SELECT id, created_at, expires_at, source, command, exit_code, "
                f"content, content_hash, content_bytes, promoted, promoted_to, "
                f"distilled, metadata FROM {EPHEMERAL_TABLE}"
            ).fetchall()
            if not rows:
                return 0
            # Insert into dest, ignoring id collisions (re-id on insert).
            for r in rows:
                dest_conn.execute(
                    f"INSERT INTO {EPHEMERAL_TABLE} "
                    f"(created_at, expires_at, source, command, exit_code, content, "
                    f"content_hash, content_bytes, promoted, promoted_to, distilled, metadata) "
                    f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    r[1:])
            return len(rows)
        finally:
            src.close()
    except Exception:
        return 0


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
        # Best-effort migration from the legacy .index.sqlite3 table (only if
        # the dedicated DB is empty and the legacy table exists). This is a
        # one-time, lightweight copy — no heavy migration framework for
        # short-lived TTL data.
        try:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {EPHEMERAL_TABLE}").fetchone()[0]
            if count == 0 and _legacy_index_has_table(rag_dir):
                _migrate_legacy_table(rag_dir, conn)
                conn.commit()
        except Exception:
            pass
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

    Truncates content to max_record_bytes (byte-safe UTF-8). Enforces
    max_records and max_bytes (hard cap: evict oldest until
    SUM(content_bytes) <= max_bytes after every insert). Scans content,
    command, and metadata for secrets BEFORE SQLite storage — secrets are
    redacted and never written to the DB.
    """
    # Truncate content (byte-safe: decode the max bytes first, then slice)
    content_bytes = len(content.encode("utf-8"))
    if content_bytes > max_record_bytes:
        content = content.encode("utf-8")[:max_record_bytes // 2].decode("utf-8", "ignore")
        content = content.rstrip() + "\n... [truncated] ...\n"
        content_bytes = len(content.encode("utf-8"))

    # Privacy: scan/redact content, command, and metadata BEFORE storage.
    # Same secret patterns as durable remember() — secrets never hit the DB.
    content = _redact(content, "content") or ""
    content_bytes = len(content.encode("utf-8"))
    command = _redact(command, "command")
    if metadata:
        meta_json_str = json.dumps(metadata)
        if _scan_secrets(meta_json_str):
            metadata = {"_redacted": "metadata contained a potential secret"}
    else:
        metadata = None

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

        # Enforce max_records: evict oldest until count <= max_records.
        count = conn.execute(
            f"SELECT COUNT(*) FROM {EPHEMERAL_TABLE}").fetchone()[0]
        if count > max_records:
            conn.execute(
                f"DELETE FROM {EPHEMERAL_TABLE} WHERE id IN "
                f"(SELECT id FROM {EPHEMERAL_TABLE} ORDER BY created_at ASC LIMIT ?)",
                (count - max_records,))

        # Enforce max_bytes: HARD CAP. Evict oldest until
        # SUM(content_bytes) <= max_bytes. Never a fixed "50" — evict as
        # many as needed (including the just-inserted row if it alone
        # exceeds max_bytes).
        while True:
            total = conn.execute(
                f"SELECT COALESCE(SUM(content_bytes), 0) FROM {EPHEMERAL_TABLE}"
            ).fetchone()[0]
            if total <= max_bytes:
                break
            # Evict the single oldest observation.
            row = conn.execute(
                f"SELECT id FROM {EPHEMERAL_TABLE} "
                f"ORDER BY created_at ASC LIMIT 1").fetchone()
            if row is None:
                break  # table empty — nothing to evict
            conn.execute(
                f"DELETE FROM {EPHEMERAL_TABLE} WHERE id = ?", (row[0],))

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