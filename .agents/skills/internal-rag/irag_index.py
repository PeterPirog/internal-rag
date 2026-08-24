#!/usr/bin/env python3
"""Optional SQLite FTS5 index for INTERNAL_RAG sparse retrieval acceleration.

This module is a cache layer — Markdown files in INTERNAL_RAG/ remain the
single source of truth. Deleting the SQLite database must never cause memory
loss; the index can always be rebuilt from Markdown.

Requirements:
- Python 3.8+ standard library sqlite3 (always available).
- FTS5 is optional: if the runtime sqlite3 lacks FTS5, the module reports
  capability=False and irag.py falls back to the pure-Python BM25 retriever.

Schema version: PRAGMA user_version
- v0: no database (fresh)
- v1: documents, chunks, usage tables (+ optional fts5 virtual tables)

Location: INTERNAL_RAG/.index.sqlite3
"""
from __future__ import annotations
import datetime as _dt
import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = 1


def _canonical_content(text: str, fm: Dict[str, Any]) -> str:
    """Compute canonical content for hashing — excludes last_accessed/access_count."""
    # Strip frontmatter and last_accessed/usage fields
    fm_clean = dict(fm)
    fm_clean.pop("last_accessed", None)
    fm_clean.pop("access_count", None)
    # Sort keys for determinism
    parts = []
    for k in sorted(fm_clean.keys()):
        v = fm_clean[k]
        if isinstance(v, list):
            v = ",".join(str(x) for x in v)
        parts.append(f"{k}={v}")
    body_start = text.find("\n---", 4)
    body = text[body_start + 4:].strip() if body_start >= 0 else text
    return "\n".join(parts) + "\n" + body


def content_hash(text: str, fm: Dict[str, Any]) -> str:
    """SHA-256 of canonical content (excludes usage metadata)."""
    canonical = _canonical_content(text, fm)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:72] or "memory"


def _extract_title(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _tags_to_text(fm: Dict[str, Any]) -> str:
    tags = fm.get("tags", [])
    if isinstance(tags, str):
        return tags
    if isinstance(tags, list):
        return " ".join(str(t) for t in tags)
    return ""


def _normalize_path(p: Path, root: Path) -> str:
    try:
        return str(p.relative_to(root)).replace("\\", "/")
    except ValueError:
        # Path not under root — use absolute path as fallback
        return str(p).replace("\\", "/")


class IndexDB:
    """SQLite cache for INTERNAL_RAG memories."""

    def __init__(self, db_path: Path, root: Path):
        self.db_path = db_path
        self.root = root
        self._conn: Optional[sqlite3.Connection] = None
        self._fts5_available: Optional[bool] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self.db_path),
                isolation_level=None,  # autocommit mode; we manage txns
                timeout=10.0,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ----------------------- capability detection -----------------------

    def fts5_available(self) -> bool:
        """Check if FTS5 is available in this runtime."""
        if self._fts5_available is not None:
            return self._fts5_available
        try:
            conn = self.conn
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_test USING fts5(x)")
            conn.execute("DROP TABLE IF EXISTS _fts5_test")
            self._fts5_available = True
        except Exception:
            self._fts5_available = False
        return self._fts5_available

    # ----------------------- migrations -----------------------

    def _get_user_version(self) -> int:
        row = self.conn.execute("PRAGMA user_version").fetchone()
        return row[0] if row else 0

    def _set_user_version(self, version: int) -> None:
        self.conn.execute(f"PRAGMA user_version = {version}")

    def migrate(self) -> None:
        """Run migrations from current version to SCHEMA_VERSION."""
        current = self._get_user_version()
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"Index schema v{current} is newer than supported v{SCHEMA_VERSION}. "
                f"Upgrade irag_index.py or delete {self.db_path} to rebuild."
            )
        if current == SCHEMA_VERSION:
            return
        # v0 -> v1
        if current < 1:
            self._migrate_v0_to_v1()
            self._set_user_version(SCHEMA_VERSION)

    def _migrate_v0_to_v1(self) -> None:
        c = self.conn
        c.execute("BEGIN")
        try:
            c.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    memory_id TEXT PRIMARY KEY,
                    path TEXT UNIQUE NOT NULL,
                    content_hash TEXT NOT NULL,
                    type TEXT,
                    status TEXT,
                    created TEXT,
                    updated TEXT,
                    verified TEXT,
                    title TEXT,
                    tags_text TEXT,
                    body TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    section TEXT,
                    content_hash TEXT NOT NULL,
                    text TEXT NOT NULL,
                    FOREIGN KEY (memory_id) REFERENCES documents(memory_id) ON DELETE CASCADE
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS usage (
                    memory_id TEXT PRIMARY KEY,
                    last_accessed TEXT,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (memory_id) REFERENCES documents(memory_id) ON DELETE CASCADE
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_chunks_memory ON chunks(memory_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(type)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)")
            # FTS5 virtual table
            if self.fts5_available():
                c.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS fts_memories USING fts5(
                        memory_id UNINDEXED,
                        title,
                        tags_text,
                        path,
                        body,
                        content='documents',
                        content_rowid='rowid'
                    )
                """)
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise

    # ----------------------- CRUD -----------------------

    def rebuild(self, candidates: List[Tuple[Path, str, Dict[str, Any]]]) -> Dict[str, int]:
        """Full rebuild: drop and recreate all data from Markdown files."""
        c = self.conn
        c.execute("BEGIN")
        try:
            c.execute("DELETE FROM chunks")
            c.execute("DELETE FROM documents")
            c.execute("DELETE FROM usage")
            if self.fts5_available():
                c.execute("DELETE FROM fts_memories")
            added = 0
            for p, text, fm in candidates:
                self._upsert_document(p, text, fm, in_txn=True)
                added += 1
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
        return {"indexed": added, "fts5": self.fts5_available()}

    def sync_incremental(self, candidates: List[Tuple[Path, str, Dict[str, Any]]]) -> Dict[str, int]:
        """Incremental sync: add new, update changed, remove deleted."""
        c = self.conn
        added = 0
        updated = 0
        deleted = 0
        # Build set of current paths
        current_paths = set()
        for p, text, fm in candidates:
            rel = _normalize_path(p, self.root)
            current_paths.add(rel)
            new_hash = content_hash(text, fm)
            row = c.execute(
                "SELECT content_hash FROM documents WHERE path=?", (rel,)
            ).fetchone()
            if row is None:
                c.execute("BEGIN")
                try:
                    self._upsert_document(p, text, fm, in_txn=True)
                    c.execute("COMMIT")
                    added += 1
                except Exception:
                    c.execute("ROLLBACK")
                    raise
            elif row["content_hash"] != new_hash:
                c.execute("BEGIN")
                try:
                    self._upsert_document(p, text, fm, in_txn=True)
                    c.execute("COMMIT")
                    updated += 1
                except Exception:
                    c.execute("ROLLBACK")
                    raise
        # Remove deleted
        rows = c.execute("SELECT path, memory_id FROM documents").fetchall()
        for row in rows:
            if row["path"] not in current_paths:
                c.execute("BEGIN")
                try:
                    self._delete_document(row["memory_id"], in_txn=True)
                    c.execute("COMMIT")
                    deleted += 1
                except Exception:
                    c.execute("ROLLBACK")
                    raise
        return {"added": added, "updated": updated, "deleted": deleted,
                "fts5": self.fts5_available()}

    def _upsert_document(self, p: Path, text: str, fm: Dict[str, Any],
                         in_txn: bool = False) -> None:
        c = self.conn
        rel = _normalize_path(p, self.root)
        mem_id = str(fm.get("id", ""))
        if not mem_id:
            mem_id = rel
        chash = content_hash(text, fm)
        title = _extract_title(text)
        tags_text = _tags_to_text(fm)
        body_start = text.find("\n---", 4)
        body = text[body_start + 4:].strip() if body_start >= 0 else text
        mtype = str(fm.get("type", ""))
        status = str(fm.get("status", ""))
        created = str(fm.get("created", ""))
        updated_val = str(fm.get("updated", ""))
        verified = str(fm.get("verified", ""))
        # Delete existing
        self._delete_document(mem_id, in_txn=True)
        # Insert document
        c.execute("""
            INSERT INTO documents (memory_id, path, content_hash, type, status,
                                   created, updated, verified, title, tags_text, body)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (mem_id, rel, chash, mtype, status, created, updated_val, verified,
              title, tags_text, body))
        # Insert chunk (single chunk for now)
        chunk_id = f"{mem_id}-c0"
        c.execute("""
            INSERT INTO chunks (chunk_id, memory_id, ordinal, section, content_hash, text)
            VALUES (?,?,0,'full',?,?)
        """, (chunk_id, mem_id, chash, body))
        # Insert usage if not exists
        c.execute("INSERT OR IGNORE INTO usage (memory_id, last_accessed, access_count) VALUES (?,?,0)",
                  (mem_id, str(fm.get("last_accessed", ""))))
        # FTS5
        if self.fts5_available():
            c.execute("INSERT INTO fts_memories (memory_id, title, tags_text, path, body) VALUES (?,?,?,?,?)",
                      (mem_id, title, tags_text, rel, body))

    def _delete_document(self, mem_id: str, in_txn: bool = False) -> None:
        c = self.conn
        c.execute("DELETE FROM chunks WHERE memory_id=?", (mem_id,))
        c.execute("DELETE FROM usage WHERE memory_id=?", (mem_id,))
        c.execute("DELETE FROM documents WHERE memory_id=?", (mem_id,))
        if self.fts5_available():
            c.execute("DELETE FROM fts_memories WHERE memory_id=?", (mem_id,))

    def record_access(self, mem_id: str) -> None:
        """Increment access count and update last_accessed."""
        c = self.conn
        today = _dt.date.today().isoformat()
        c.execute("BEGIN")
        try:
            row = c.execute("SELECT access_count FROM usage WHERE memory_id=?", (mem_id,)).fetchone()
            if row:
                c.execute("UPDATE usage SET last_accessed=?, access_count=? WHERE memory_id=?",
                          (today, row["access_count"] + 1, mem_id))
            else:
                c.execute("INSERT INTO usage (memory_id, last_accessed, access_count) VALUES (?,?,1)",
                          (mem_id, today))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")

    # ----------------------- FTS5 search -----------------------

    def fts5_search(self, query: str, limit: int,
                    types: Optional[List[str]] = None,
                    statuses: Optional[List[str]] = None
                    ) -> Optional[List[Tuple[float, str, str]]]:
        """Search using FTS5 bm25(). Returns (bm25_score, memory_id, path) tuples.
        bm25() returns lower scores = better matches (negative values).
        We negate so higher = better.
        Returns None if FTS5 not available."""
        if not self.fts5_available():
            return None
        # Build query: use OR for terms, MATCH syntax
        # Escape double quotes and build a simple OR query
        terms = re.findall(r"[A-Za-z0-9_./:@+-]{2,}", query)
        if not terms:
            return []
        fts_query = " OR ".join(f'"{t}"' for t in terms)
        sql = """
            SELECT fts_memories.memory_id, fts_memories.path,
                   bm25(fts_memories, 10.0, 8.0, 5.0, 1.0) as score
            FROM fts_memories
            JOIN documents ON fts_memories.memory_id = documents.memory_id
            WHERE fts_memories MATCH ?
        """
        params: list = [fts_query]
        if types:
            placeholders = ",".join("?" for _ in types)
            sql += f" AND documents.type IN ({placeholders})"
            params.extend(types)
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            sql += f" AND documents.status IN ({placeholders})"
            params.extend(statuses)
        sql += " ORDER BY score ASC LIMIT ?"
        params.append(limit)
        try:
            rows = self.conn.execute(sql, params).fetchall()
            # bm25 returns negative values (lower = better), negate for consistency
            return [(-float(r["score"]), r["memory_id"], r["path"]) for r in rows]
        except Exception:
            return None

    # ----------------------- status & vacuum -----------------------

    def status(self) -> Dict[str, Any]:
        """Return index status info."""
        try:
            ver = self._get_user_version()
        except Exception:
            ver = -1
        try:
            n_docs = self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        except Exception:
            n_docs = 0
        try:
            n_chunks = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        except Exception:
            n_chunks = 0
        db_size = 0
        try:
            db_size = self.db_path.stat().st_size
        except Exception:
            pass
        return {
            "schema_version": ver,
            "fts5_available": self.fts5_available(),
            "indexed_memories": n_docs,
            "chunks": n_chunks,
            "db_path": str(self.db_path),
            "db_size_bytes": db_size,
            "sqlite_version": sqlite3.sqlite_version,
        }

    def vacuum(self) -> None:
        """VACUUM the database to reclaim space."""
        self.conn.execute("VACUUM")

    def stale_check(self, candidates: List[Tuple[Path, str, Dict[str, Any]]]) -> Dict[str, int]:
        """Check for stale/missing rows."""
        current_hashes: Dict[str, str] = {}
        current_paths = set()
        for p, text, fm in candidates:
            rel = _normalize_path(p, self.root)
            current_paths.add(rel)
            current_hashes[rel] = content_hash(text, fm)
        rows = self.conn.execute("SELECT path, content_hash FROM documents").fetchall()
        stale = 0
        missing = 0
        for row in rows:
            if row["path"] not in current_paths:
                missing += 1
            elif row["content_hash"] != current_hashes.get(row["path"], ""):
                stale += 1
        return {"stale": stale, "missing": missing, "total_indexed": len(rows),
                "total_markdown": len(current_paths)}


def open_index(root: Path) -> Optional[IndexDB]:
    """Open or create the index database. Returns None if path is not usable."""
    db_path = root / "INTERNAL_RAG" / ".index.sqlite3"
    try:
        idx = IndexDB(db_path, root)
        idx.migrate()
        return idx
    except Exception:
        return None