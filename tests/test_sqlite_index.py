#!/usr/bin/env python3
"""Tests for the optional SQLite FTS5 index.

Uses only the standard library (unittest, sqlite3, tempfile).
No external dependencies.
"""
from __future__ import annotations
import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple

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


def _load_fixtures() -> List[Tuple[Path, str, Dict[str, Any]]]:
    candidates = []
    for p in sorted(FIXTURES_DIR.rglob("*.md")):
        text = p.read_text(encoding="utf-8")
        fm = irag.parse_fm(text)
        candidates.append((p, text, fm))
    return candidates


class TestIndexDB(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="irag-idx-test-"))
        self.root = self.tmp / "project"
        self.rag = self.root / "INTERNAL_RAG"
        self.rag.mkdir(parents=True, exist_ok=True)
        (self.root / ".git").mkdir(exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_idx(self) -> irag_index.IndexDB:
        db_path = self.rag / ".index.sqlite3"
        idx = irag_index.IndexDB(db_path, self.root)
        idx.migrate()
        return idx

    def test_fts5_capability_detection(self):
        """FTS5 capability should be detected (or not) without error."""
        idx = self._make_idx()
        result = idx.fts5_available()
        self.assertIsInstance(result, bool)
        idx.close()

    def test_rebuild_empty(self):
        """Rebuild with no candidates should produce 0 documents."""
        idx = self._make_idx()
        result = idx.rebuild([])
        self.assertEqual(result["indexed"], 0)
        st = idx.status()
        self.assertEqual(st["indexed_memories"], 0)
        idx.close()

    def test_rebuild_nonempty(self):
        """Rebuild with fixtures should index all documents."""
        cands = _load_fixtures()
        idx = self._make_idx()
        result = idx.rebuild(cands)
        self.assertEqual(result["indexed"], len(cands))
        st = idx.status()
        self.assertEqual(st["indexed_memories"], len(cands))
        idx.close()

    def test_schema_version(self):
        """After migration, schema version should be 1."""
        idx = self._make_idx()
        st = idx.status()
        self.assertEqual(st["schema_version"], 1)
        idx.close()

    def test_content_hash_excludes_usage(self):
        """Content hash should not change when last_accessed is updated."""
        fm = {"id": "test", "type": "knowledge", "status": "active",
              "created": "2024-01-01", "last_accessed": "2024-01-10"}
        text = "---\nid: test\n---\n\n# Test\n\nBody."
        h1 = irag_index.content_hash(text, fm)
        fm["last_accessed"] = "2024-12-31"
        h2 = irag_index.content_hash(text, fm)
        self.assertEqual(h1, h2)

    def test_content_hash_changes_with_body(self):
        """Content hash should change when body changes."""
        fm = {"id": "test", "type": "knowledge", "status": "active", "created": "2024-01-01"}
        text1 = "---\nid: test\n---\n\n# Test\n\nBody A."
        text2 = "---\nid: test\n---\n\n# Test\n\nBody B."
        h1 = irag_index.content_hash(text1, fm)
        h2 = irag_index.content_hash(text2, fm)
        self.assertNotEqual(h1, h2)

    def test_incremental_add(self):
        """Incremental sync should add new documents."""
        cands = _load_fixtures()[:10]
        idx = self._make_idx()
        idx.rebuild(cands)
        # Add more
        cands2 = _load_fixtures()[:15]
        result = idx.sync_incremental(cands2)
        self.assertEqual(result["added"], 5)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["deleted"], 0)
        st = idx.status()
        self.assertEqual(st["indexed_memories"], 15)
        idx.close()

    def test_incremental_update(self):
        """Incremental sync should detect changed documents."""
        cands = _load_fixtures()[:5]
        idx = self._make_idx()
        idx.rebuild(cands)
        # Modify one document
        modified = list(cands)
        p, text, fm = modified[0]
        new_text = text + "\n\n## Update\n\nNew content."
        modified[0] = (p, new_text, irag.parse_fm(new_text))
        result = idx.sync_incremental(modified)
        self.assertEqual(result["updated"], 1)
        idx.close()

    def test_incremental_delete(self):
        """Incremental sync should remove deleted documents."""
        cands = _load_fixtures()[:10]
        idx = self._make_idx()
        idx.rebuild(cands)
        # Remove some
        cands2 = cands[:5]
        result = idx.sync_incremental(cands2)
        self.assertEqual(result["deleted"], 5)
        st = idx.status()
        self.assertEqual(st["indexed_memories"], 5)
        idx.close()

    def test_fts5_search_returns_results(self):
        """FTS5 search (if available) should return matching documents."""
        cands = _load_fixtures()
        idx = self._make_idx()
        idx.rebuild(cands)
        if idx.fts5_available():
            results = idx.fts5_search("postgres database", 5)
            self.assertIsNotNone(results)
            self.assertTrue(len(results) > 0)
        else:
            self.skipTest("FTS5 not available in this runtime")
        idx.close()

    def test_fts5_search_exact_identifier(self):
        """FTS5 should find exact identifiers like refresh_token_cache."""
        cands = _load_fixtures()
        idx = self._make_idx()
        idx.rebuild(cands)
        if idx.fts5_available():
            results = idx.fts5_search("refresh_token_cache", 5)
            self.assertIsNotNone(results)
            self.assertTrue(len(results) > 0)
            # Check that the right memory is in results
            found = any("refresh-token-cache" in r[2] or "refresh" in r[1].lower() for r in results)
            self.assertTrue(found, "refresh_token_cache not found in FTS5 results")
        else:
            self.skipTest("FTS5 not available")
        idx.close()

    def test_fts5_search_with_type_filter(self):
        """FTS5 search with type filter should only return matching types."""
        cands = _load_fixtures()
        idx = self._make_idx()
        idx.rebuild(cands)
        if idx.fts5_available():
            results = idx.fts5_search("postgres", 10, types=["decision"])
            self.assertIsNotNone(results)
            # All results should be decisions (check via DB)
            for score, mem_id, path in results:
                row = idx.conn.execute("SELECT type FROM documents WHERE memory_id=?", (mem_id,)).fetchone()
                if row:
                    self.assertEqual(row["type"], "decision")
        else:
            self.skipTest("FTS5 not available")
        idx.close()

    def test_fts5_search_with_status_filter(self):
        """FTS5 search with status filter should only return matching statuses."""
        cands = _load_fixtures()
        idx = self._make_idx()
        idx.rebuild(cands)
        if idx.fts5_available():
            results = idx.fts5_search("api", 10, statuses=["active"])
            self.assertIsNotNone(results)
            for score, mem_id, path in results:
                row = idx.conn.execute("SELECT status FROM documents WHERE memory_id=?", (mem_id,)).fetchone()
                if row:
                    self.assertEqual(row["status"], "active")
        else:
            self.skipTest("FTS5 not available")
        idx.close()

    def test_delete_index_and_rebuild(self):
        """Deleting .index.sqlite3 and rebuilding should work."""
        cands = _load_fixtures()
        idx = self._make_idx()
        idx.rebuild(cands)
        idx.close()
        db_path = self.rag / ".index.sqlite3"
        self.assertTrue(db_path.exists())
        db_path.unlink()
        self.assertFalse(db_path.exists())
        # Rebuild
        idx2 = self._make_idx()
        idx2.rebuild(cands)
        st = idx2.status()
        self.assertEqual(st["indexed_memories"], len(cands))
        idx2.close()

    def test_stale_check(self):
        """Stale check should detect changed and missing documents."""
        cands = _load_fixtures()[:10]
        idx = self._make_idx()
        idx.rebuild(cands)
        # Simulate stale: pass fewer candidates (missing)
        cands2 = cands[:5]
        stale = idx.stale_check(cands2)
        self.assertEqual(stale["missing"], 5)
        self.assertEqual(stale["stale"], 0)
        idx.close()

    def test_vacuum(self):
        """VACUUM should not error."""
        cands = _load_fixtures()[:5]
        idx = self._make_idx()
        idx.rebuild(cands)
        idx.vacuum()
        idx.close()

    def test_record_access(self):
        """record_access should increment access count."""
        cands = _load_fixtures()[:3]
        idx = self._make_idx()
        idx.rebuild(cands)
        mem_id = str(cands[0][2].get("id", ""))
        idx.record_access(mem_id)
        idx.record_access(mem_id)
        row = idx.conn.execute("SELECT access_count FROM usage WHERE memory_id=?", (mem_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["access_count"], 2)
        idx.close()

    def test_newer_schema_error(self):
        """A newer schema version should produce a clear error."""
        idx = self._make_idx()
        idx.conn.execute("PRAGMA user_version = 999")
        idx.close()
        # Reopen should fail with clear error
        db_path = self.rag / ".index.sqlite3"
        idx2 = irag_index.IndexDB(db_path, self.root)
        with self.assertRaises(RuntimeError) as ctx:
            idx2.migrate()
        self.assertIn("newer than supported", str(ctx.exception))
        idx2.close()


class TestSearchDoesNotMutateMarkdown(unittest.TestCase):

    def test_search_does_not_modify_markdown(self):
        """Running search should not modify any Markdown files."""
        # Use fixtures — record before/after hashes
        fixture_files = list(FIXTURES_DIR.rglob("*.md"))
        before = {}
        for p in fixture_files:
            before[str(p)] = p.read_bytes()
        # Run search through irag (patched ROOT)
        original_root = irag.ROOT
        original_rag = irag.RAG
        irag.ROOT = FIXTURES_DIR.parent
        irag.RAG = FIXTURES_DIR
        try:
            cfg = {"retrieval": {"limit": 5, "mmr_lambda": 1.0, "min_score": 0.0,
                                  "mode": "sparse", "embeddings": "off",
                                  "rrf_k": 60, "sparse_weight": 1.0, "dense_weight": 1.0,
                                  "candidate_multiplier": 4}}
            results = irag._search_with_cfg("postgres database", 5, cfg)
            self.assertTrue(len(results) > 0)
        finally:
            irag.ROOT = original_root
            irag.RAG = original_rag
        # Verify no changes
        for p in fixture_files:
            after = p.read_bytes()
            self.assertEqual(before[str(p)], after, f"Markdown file was modified: {p}")


if __name__ == "__main__":
    unittest.main()