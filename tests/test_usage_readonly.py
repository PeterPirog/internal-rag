#!/usr/bin/env python3
"""Tests for read-only usage tracking (last_accessed/access_count in SQLite usage table).

Covers:
- search does NOT change mtime or content hash of Markdown files
- usage count grows in the DB
- old frontmatter last_accessed is migrated
- search works when usage DB is unavailable
- index rebuild preserves usage without explicit reset
- content_hash excludes usage fields
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import List, Tuple

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
IRAG_PATH = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag.py"
INDEX_PATH = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag_index.py"
FIXTURES_DIR = HERE / "fixtures" / "retrieval"

_spec = importlib.util.spec_from_file_location("irag_mod", str(IRAG_PATH))
irag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(irag)

_spec_idx = importlib.util.spec_from_file_location("irag_index_mod", str(INDEX_PATH))
irag_index = importlib.util.module_from_spec(_spec_idx)
_spec_idx.loader.exec_module(irag_index)


def _load_fixtures() -> List[Tuple[Path, str, dict]]:
    out = []
    for p in sorted(FIXTURES_DIR.rglob("*.md")):
        text = p.read_text(encoding="utf-8")
        out.append((p, text, irag.parse_fm(text)))
    return out


class SearchCtx:
    """Redirects irag.ROOT/RAG to a sandbox dir for isolated search runs."""

    def __init__(self, sandbox: Path):
        self.sandbox = sandbox
        self.rag = sandbox / "INTERNAL_RAG"
        self.rag.mkdir(parents=True, exist_ok=True)
        (self.rag / "knowledge").mkdir(exist_ok=True)
        for p, text, fm in _load_fixtures():
            (self.rag / "knowledge" / p.name).write_text(text, encoding="utf-8")
        self._old = None
        self._idx = []  # track opened IndexDB handles for cleanup

    def __enter__(self):
        self._old = (irag.ROOT, irag.RAG, irag.CONFIG_PATH)
        irag.ROOT = self.sandbox
        irag.RAG = self.rag
        irag.CONFIG_PATH = self.sandbox / ".irag.yml"  # absent -> defaults
        self._orig_open = irag._open_sqlite_index
        irag._open_sqlite_index = self._tracked_open
        return self

    def _tracked_open(self):
        idx = self._orig_open()
        if idx is not None:
            self._idx.append(idx)
        return idx

    def _search(self, query="docker postgres"):
        cfg = {"retrieval": {"limit": 5, "mode": "sparse", "embeddings": "off",
                              "mmr_lambda": 1.0, "min_score": 0.0, "rrf_k": 60,
                              "sparse_weight": 1.0, "dense_weight": 1.0,
                              "candidate_multiplier": 4}}
        return irag._search_with_cfg(query, 5, cfg)

    def build_index(self):
        cands = [(p, p.read_text(encoding="utf-8"), irag.parse_fm(p.read_text(encoding="utf-8")))
                 for p in sorted(self.rag.rglob("*.md"))]
        idx = irag_index.IndexDB(self.rag / ".index.sqlite3", self.sandbox)
        self._idx.append(idx)
        idx.migrate()
        idx.rebuild(cands)
        return idx

    def sandbox_cands(self, limit=None):
        paths = sorted(self.rag.rglob("*.md"))
        if limit:
            paths = paths[:limit]
        return [(p, p.read_text(encoding="utf-8"), irag.parse_fm(p.read_text(encoding="utf-8")))
                for p in paths]

    def __exit__(self, *a):
        for idx in self._idx:
            try:
                idx.close()
            except Exception:
                pass
        self._idx = []
        irag._open_sqlite_index = self._orig_open
        irag.ROOT, irag.RAG, irag.CONFIG_PATH = self._old


class TestSearchReadOnly(unittest.TestCase):

    def test_search_does_not_modify_markdown(self):
        """Two searches must not change mtime or content hash of Markdown files."""
        with tempfile.TemporaryDirectory(prefix="irag-ro-") as td:
            with SearchCtx(Path(td)) as ctx:
                files = list(ctx.rag.rglob("*.md"))
                before = {str(p): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in files}
                ctx._search()
                ctx._search("auth cache token")
                after = {str(p): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in files}
                self.assertEqual(before, after, "search mutated Markdown files")

    def test_usage_count_grows_in_db(self):
        """Usage access_count should increase across searches (in SQLite, not Markdown)."""
        with tempfile.TemporaryDirectory(prefix="irag-uc-") as td:
            with SearchCtx(Path(td)) as ctx:
                ctx.build_index()
                results = ctx._search()
                self.assertTrue(results)
                mid = str(results[0][2].get("id", str(results[0][1])))
                idx = irag._open_sqlite_index()
                r1 = idx.conn.execute("SELECT access_count FROM usage WHERE memory_id=?", (mid,)).fetchone()
                self.assertIsNotNone(r1, "no usage row after first search")
                cnt1 = r1["access_count"]
                ctx._search()
                r2 = idx.conn.execute("SELECT access_count FROM usage WHERE memory_id=?", (mid,)).fetchone()
                self.assertGreater(r2["access_count"], cnt1, "usage count did not grow")


class TestUsageMigration(unittest.TestCase):

    def _setup(self, ctx):
        target = sorted(ctx.rag.glob("knowledge/*.md"))[0]
        text = target.read_text(encoding="utf-8")
        fm = irag.parse_fm(text)
        fm["last_accessed"] = "2023-01-15"
        body_start = text.find("\n---", 4)
        body = text[body_start + 4:].lstrip("\n") if body_start >= 0 else text
        target.write_text(irag.write_fm(fm) + "\n" + body, encoding="utf-8")
        return target, str(fm.get("id", ""))

    def test_dry_run_reports_and_changes_nothing(self):
        """--dry-run reports the entry but does not write DB or strip Markdown."""
        with tempfile.TemporaryDirectory(prefix="irag-mig-dry-") as td:
            with SearchCtx(Path(td)) as ctx:
                target, mid = self._setup(ctx)
                text_before = target.read_text(encoding="utf-8")
                args = type("A", (), {"dry_run": True, "apply": False, "strip": True, "json": False})()
                self.assertEqual(irag.migrate_usage_cmd(args), 0)
                self.assertEqual(target.read_text(encoding="utf-8"), text_before)
                idx = irag._open_sqlite_index()
                row = None
                if idx is not None:
                    row = idx.conn.execute(
                        "SELECT last_accessed FROM usage WHERE memory_id=?", (mid,)).fetchone()
                if row is not None:
                    self.assertNotEqual(row["last_accessed"], "2023-01-15",
                                        "dry-run must not import")
                self.assertIn("2023-01-15", target.read_text(encoding="utf-8"))

    def test_apply_imports_and_strips_with_backup(self):
        """--apply --strip writes DB, strips frontmatter, creates backup, reports files."""
        with tempfile.TemporaryDirectory(prefix="irag-mig-ap-") as td:
            with SearchCtx(Path(td)) as ctx:
                # Build the index first so the FK target (documents) exists
                ctx.build_index()
                target, mid = self._setup(ctx)
                # Simulate an index that predates auto-seed: DB lacks this value
                idx0 = irag._open_sqlite_index()
                idx0.conn.execute("DELETE FROM usage WHERE memory_id=?", (mid,))
                idx0.close()
                idx0 = irag._open_sqlite_index()
                row = idx0.conn.execute(
                    "SELECT memory_id, last_accessed FROM usage WHERE memory_id=?", (mid,)).fetchone()
                idx0.close()
                if row is not None:
                    self.fail(f"index auto-seeded usage before migration test: {dict(row)}")
                args = type("A", (), {"dry_run": False, "apply": True, "strip": True, "json": True})()
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = irag.migrate_usage_cmd(args)
                self.assertEqual(rc, 0)
                report = json.loads(buf.getvalue())
                self.assertGreaterEqual(report["imported"], 1)
                self.assertGreaterEqual(report["stripped"], 1)
                self.assertIn(str(target.relative_to(ctx.sandbox)), report["changed_files"])
                self.assertTrue(report["backups"], "no backup created")
                # Markdown no longer has last_accessed
                fm_after = irag.parse_fm(target.read_text(encoding="utf-8"))
                self.assertNotIn("last_accessed", fm_after)
                # Backup exists and still contains the old field
                bak = ctx.sandbox / report["backups"][0]
                self.assertTrue(bak.exists())
                self.assertIn("2023-01-15", bak.read_text(encoding="utf-8"))
                # DB holds the historical date with count 0
                idx = irag._open_sqlite_index()
                row = idx.conn.execute(
                    "SELECT last_accessed, access_count FROM usage WHERE memory_id=?",
                    (mid,)).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["last_accessed"], "2023-01-15")
                self.assertEqual(row["access_count"], 0)

    def test_search_works_when_db_unavailable(self):
        """Search must succeed even if the SQLite usage DB cannot be opened."""
        with tempfile.TemporaryDirectory(prefix="irag-nodb-") as td:
            with SearchCtx(Path(td)) as ctx:
                irag._open_sqlite_index = lambda: None
                results = ctx._search()
                self.assertTrue(results, "search returned nothing without usage DB")


class TestRebuildPreservesUsage(unittest.TestCase):

    def test_rebuild_preserves_usage_by_default(self):
        """Rebuild must keep usage rows unless reset_usage=True."""
        with tempfile.TemporaryDirectory(prefix="irag-rb-") as td:
            with SearchCtx(Path(td)) as ctx:
                idx = ctx.build_index()
                cands = [(p, p.read_text(encoding="utf-8"), irag.parse_fm(p.read_text(encoding="utf-8")))
                         for p in sorted(ctx.rag.rglob("*.md"))]
                mid = str(cands[0][2].get("id", str(cands[0][0])))
                idx.record_access(mid)
                row1 = idx.conn.execute("SELECT last_accessed, access_count FROM usage WHERE memory_id=?", (mid,)).fetchone()
                self.assertGreaterEqual(row1["access_count"], 1)
                cnt1 = row1["access_count"]
                # Rebuild (no reset)
                idx.rebuild(cands)
                row2 = idx.conn.execute("SELECT last_accessed, access_count FROM usage WHERE memory_id=?", (mid,)).fetchone()
                self.assertIsNotNone(row2, "usage row lost after rebuild")
                self.assertEqual(row2["access_count"], row1["access_count"],
                                 "usage count lost after rebuild")
                # Explicit reset re-seeds from frontmatter only (fixture may carry a legacy value)
                idx.rebuild(ctx.sandbox_cands(), reset_usage=True)
                row3 = idx.conn.execute("SELECT access_count, last_accessed FROM usage WHERE memory_id=?", (mid,)).fetchone()
                if row3 is not None:
                    self.assertEqual(row3["access_count"], 0)
                    self.assertIn(row3["last_accessed"], (None, "", cands[0][2].get("last_accessed", "")))

    def test_sync_upsert_preserves_usage(self):
        """Upserting a document (update path) must not reset its usage row."""
        with tempfile.TemporaryDirectory(prefix="irag-sync-") as td:
            with SearchCtx(Path(td)) as ctx:
                idx = ctx.build_index()
                cands = [(p, p.read_text(encoding="utf-8"), irag.parse_fm(p.read_text(encoding="utf-8")))
                         for p in sorted(ctx.rag.rglob("*.md"))][:5]
                mid = str(cands[0][2].get("id", str(cands[0][0])))
                idx.record_access(mid)
                idx.record_access(mid)
                cnt1 = idx.conn.execute("SELECT access_count FROM usage WHERE memory_id=?", (mid,)).fetchone()["access_count"]
                self.assertGreaterEqual(cnt1, 2)
                # Modify document content -> update path in sync_incremental
                p, text, fm = ctx.sandbox_cands(5)[0]
                p.write_text(text + "\n\n## Note\n\nExtra.", encoding="utf-8")
                idx.sync_incremental(ctx.sandbox_cands(5))
                row = idx.conn.execute("SELECT access_count FROM usage WHERE memory_id=?", (mid,)).fetchone()
                self.assertIsNotNone(row, "usage row lost after sync update")
                self.assertEqual(row["access_count"], cnt1, "usage count changed on content update")


class TestContentHashExcludesUsage(unittest.TestCase):

    def test_hash_stable_across_usage_fields(self):
        fm = {"id": "x", "type": "knowledge", "status": "active",
              "last_accessed": "2020-01-01", "access_count": 99}
        text = "---\nid: x\n---\n\n# T\n\nBody."
        h1 = irag_index.content_hash(text, fm)
        fm["last_accessed"] = "2026-12-31"
        fm["access_count"] = 0
        h2 = irag_index.content_hash(text, fm)
        self.assertEqual(h1, h2)


if __name__ == "__main__":
    unittest.main()
