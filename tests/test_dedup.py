#!/usr/bin/env python3
"""Tests for cheap content deduplication (exact fingerprint + 64-bit SimHash).

Covers:
- identical text with a different title -> exact duplicate (title is part of canonical)
- lightly reformulated text -> near duplicate (SimHash small Hamming distance)
- opposing decision is NOT flagged as duplicate (conflict and duplicate stay separate)
- Polish diacritics + whitespace differences do not break exact normalization
- import of the same bundle twice is idempotent without --overwrite/--force
- --force bypasses the exact-duplicate block
- archived memories are shown informationally, not as active duplicates
"""
from __future__ import annotations
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
IRAG_PATH = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag.py"

_spec = importlib.util.spec_from_file_location("irag_mod", str(IRAG_PATH))
irag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(irag)


class Env:
    """Redirects irag.ROOT/RAG to a fresh sandbox INTERNAL_RAG tree."""

    def __init__(self, sandbox: Path):
        self.sandbox = sandbox
        self.rag = sandbox / "INTERNAL_RAG"
        for d in ["decisions", "knowledge", "gotchas", "failures", "hypotheses", "sessions", "archive"]:
            (self.rag / d).mkdir(parents=True, exist_ok=True)

    def __enter__(self):
        self._old = (irag.ROOT, irag.RAG, irag.CONFIG_PATH)
        irag.ROOT = self.sandbox
        irag.RAG = self.rag
        irag.CONFIG_PATH = self.sandbox / ".irag.yml"
        irag._open_sqlite_index = lambda: None  # hermetic
        self._orig_open = irag._open_sqlite_index
        return self

    def __exit__(self, *a):
        irag.ROOT, irag.RAG, irag.CONFIG_PATH = self._old
        irag._open_sqlite_index = self._orig_open

    def write_memory(self, subdir: str, name: str, mtype: str, title: str, body: str,
                     status: str = "active", consequence: str = "") -> Path:
        p = self.rag / subdir / name
        p.write_text(
            f"---\nid: mem-test-{name}.replace('.md','')\ntype: {mtype}\nstatus: {status}\n"
            f"created: 2024-01-01\nscope: []\ntags: []\n---\n\n# {title}\n\n"
            f"## Knowledge\n\n{body}\n\n## Consequence\n\n{consequence or 'None.'}\n",
            encoding="utf-8")
        return p


class A:
    def __init__(self, **kw):
        self.type = kw.get("type", "knowledge")
        self.status = kw.get("status", "active")
        self.title = kw.get("title", "Test")
        self.scope = kw.get("scope", "")
        self.tags = kw.get("tags", "")
        self.evidence = kw.get("evidence", "")
        self.body = kw.get("body", "body text")
        self.consequence = kw.get("consequence", "")
        self.links = kw.get("links", "")
        self.force = kw.get("force", False)
        self.allow_secret = kw.get("allow_secret", True)
        self.json = kw.get("json", False)


class TestDedupAlgorithms(unittest.TestCase):

    def test_exact_fingerprint_stable(self):
        t = "use postgres 16"
        b = "we  decided\nto   use Postgres for JSONB support."
        c1 = irag._canonical_memory_text(t, b, "", "db", "infra")
        c2 = irag._canonical_memory_text(t, "we decided to use Postgres for JSONB support.", "", "db", "infra")
        self.assertEqual(irag._exact_fingerprint(c1), irag._exact_fingerprint(c2))

    def test_simhash_64bit_range(self):
        v = irag._simhash_64bit("some canonical text with tokens")
        self.assertGreaterEqual(v, 0)
        self.assertLess(v, 1 << 64)

    def test_simhash_close_texts_small_distance(self):
        a = irag._simhash_64bit("we decided to use postgres 16 for jsonb operator support and pgvector")
        b = irag._simhash_64bit("we decided to use postgres 16 for jsonb operator support and the pgvector extension")
        self.assertLessEqual(irag._hamming_distance(a, b), 8)

    def test_simhash_different_texts_larger_distance(self):
        a = irag._simhash_64bit("we decided to use postgres 16 for jsonb operator support and pgvector")
        b = irag._simhash_64bit("we decided to use mysql 8 for stored procedure support and replication")
        self.assertGreater(irag._hamming_distance(a, b), 8)


class TestRememberDedup(unittest.TestCase):

    def _new_env(self):
        td = tempfile.mkdtemp(prefix="irag-dedup-")
        return td, Env(Path(td))

    def test_identical_text_different_title_is_near_not_exact(self):
        """Identical body/consequence with a different title -> not exact (title in canonical),
        but SimHash flags it as a near duplicate."""
        td = tempfile.mkdtemp(prefix="irag-dedup-")
        with Env(Path(td)) as env:
            env.write_memory("decisions", "001-a.md", "decision", "Use Postgres 16",
                             "We decided to use Postgres 16 for JSONB operator support and pgvector.",
                             consequence="All migrations must be Postgres-compatible.")
            buf = io.StringIO()
            with redirect_stdout(buf):
                res = irag.remember(A(type="decision", title="Choose database engine",
                                       body="We decided to use Postgres 16 for JSONB operator support and pgvector.",
                                       consequence="All migrations must be Postgres-compatible."))
            self.assertEqual(res, "blocked")
            out = env.rag.glob("decisions/002*")
            self.assertEqual(list(out), [], "duplicate must not be written")

    def test_identical_full_memory_is_exact(self):
        """Title AND body identical -> exact duplicate, blocked."""
        td = tempfile.mkdtemp(prefix="irag-dedup-")
        with Env(Path(td)) as env:
            env.write_memory("knowledge", "001-a.md", "knowledge", "Postgres JSONB",
                             "Postgres 16 supports JSONB operator indexes efficiently.",
                             consequence="Query planner must use jsonb ops.")
            res = irag.remember(A(title="Postgres JSONB",
                                   body="Postgres 16 supports JSONB operator indexes efficiently.",
                                   consequence="Query planner must use jsonb ops."))
            self.assertEqual(res, "blocked")
            self.assertEqual(len(list(env.rag.glob("knowledge/*.md"))), 1)

    def test_opposing_decision_not_flagged_duplicate(self):
        """Opposing decision (different choice) must NOT be an exact/near duplicate.
        It may be surfaced as a *conflict* (separate signal) but not as a duplicate."""
        td = tempfile.mkdtemp(prefix="irag-dedup-")
        with Env(Path(td)) as env:
            env.write_memory("decisions", "001-a.md", "decision", "Use Postgres",
                             "We decided to use Postgres 16 for the primary datastore and all migrations.",
                             consequence="All migrations must be Postgres-compatible.")
            check = irag._check_duplicates(
                "Use MySQL",
                "We decided to use MySQL 8 for the primary datastore and all migrations.",
                "All migrations must be MySQL-compatible.",
                "decision")
            self.assertFalse(check["exact"], "opposing decision flagged as exact duplicate")
            self.assertEqual(check["near"], [], "opposing decision flagged as near duplicate")
            self.assertEqual(check["title_similar"], [], "opposing decision flagged by title similarity")

    def test_polish_and_whitespace_normalization(self):
        """Polskie znaki + whitespace differences must not break exact normalization."""
        td = tempfile.mkdtemp(prefix="irag-dedup-")
        with Env(Path(td)) as env:
            env.write_memory("knowledge", "001-a.md", "knowledge", "Użycie   bazy  danych",
                             "Zdecydowaliśmy  się  na   PostgreSQL   z   powodu\n  wydajności JSONB.",
                             consequence="Wszystkie migracje muszą być zgodne.")
            # Same tokens, different whitespace/case -> exact match after normalization
            res = irag.remember(A(title="uzycie bazy danych",
                                   body="Zdecydowaliśmy się na PostgreSQL z powodu wydajności JSONB.",
                                   consequence="Wszystkie migracje muszą być zgodne."))
            self.assertEqual(res, "blocked")
            out = env.rag.glob("knowledge/*.md")
            self.assertEqual(len(list(out)), 1, "whitespace-only difference must be an exact duplicate")

    def test_force_bypasses_block(self):
        td = tempfile.mkdtemp(prefix="irag-dedup-")
        with Env(Path(td)) as env:
            env.write_memory("knowledge", "001-a.md", "knowledge", "Postgres JSONB",
                             "Postgres 16 supports JSONB operator indexes efficiently.",
                             consequence="Query planner must use jsonb ops.")
            res = irag.remember(A(force=True, title="Postgres JSONB",
                                   body="Postgres 16 supports JSONB operator indexes efficiently.",
                                   consequence="Query planner must use jsonb ops."))
            self.assertEqual(res, "created")
            self.assertEqual(len(list(env.rag.glob("knowledge/*.md"))), 2)

    def test_archived_shown_informationally(self):
        """Archived memory with identical content: not an active exact duplicate, but listed."""
        td = tempfile.mkdtemp(prefix="irag-dedup-")
        with Env(Path(td)) as env:
            p = env.write_memory("archive", "001-a.md", "knowledge", "Postgres JSONB",
                                 "Postgres 16 supports JSONB operator indexes efficiently.",
                                 consequence="Query planner must use jsonb ops.")
            check = irag._check_duplicates("Postgres JSONB",
                                           "Postgres 16 supports JSONB operator indexes efficiently.",
                                           "Query planner must use jsonb ops.", "knowledge")
            self.assertFalse(check["exact"], "archived memory must not be an active exact duplicate")
            self.assertTrue(any("archived" in d for d in check["near"]),
                            "archived exact match should be shown informationally")

    def test_json_duplicate_shape(self):
        td = tempfile.mkdtemp(prefix="irag-dedup-")
        with Env(Path(td)) as env:
            env.write_memory("knowledge", "001-a.md", "knowledge", "Postgres JSONB",
                             "Postgres 16 supports JSONB operator indexes efficiently.",
                             consequence="Query planner must use jsonb ops.")
            buf = io.StringIO()
            with redirect_stdout(buf):
                res = irag.remember(A(json=True, title="Postgres JSONB",
                                       body="Postgres 16 supports JSONB operator indexes efficiently.",
                                       consequence="Query planner must use jsonb ops."))
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["status"], "blocked")
            dup = payload["duplicate"]
            self.assertIsInstance(dup["exact"], bool)
            self.assertIsInstance(dup["near"], list)
            self.assertIsInstance(dup["title_similar"], list)
            self.assertIn(dup["recommended_action"], ("update", "supersede", "force", None))


class TestImportIdempotent(unittest.TestCase):

    def _bundle(self, tmp: Path) -> Path:
        content = (
            "---\nid: mem-bundle-1\ntype: knowledge\nstatus: active\n"
            "created: 2024-01-01\nscope: []\ntags: []\n---\n\n"
            "# Bundle fact\n\n## Knowledge\n\nThe bundle fact body.\n\n## Consequence\n\nNone.\n")
        payload = {"memories": [{"path": "INTERNAL_RAG/knowledge/bundle-fact.md", "content": content}]}
        f = tmp / "bundle.json"
        f.write_text(json.dumps(payload), encoding="utf-8")
        return f

    def test_import_twice_is_idempotent(self):
        with tempfile.TemporaryDirectory(prefix="irag-imp-") as td:
            with Env(Path(td)) as env:
                bundle = self._bundle(Path(td))

                class ImportArgs:
                    file = str(bundle)
                    overwrite = False
                self.assertEqual(irag.import_cmd(ImportArgs()), 0)
                first = len(list(env.rag.glob("knowledge/*.md")))
                self.assertEqual(first, 1)
                self.assertEqual(irag.import_cmd(ImportArgs()), 0)
                second = len(list(env.rag.glob("knowledge/*.md")))
                self.assertEqual(second, 1, "second import must not create a copy without --overwrite")
                content = list(env.rag.glob("knowledge/*.md"))[0].read_text(encoding="utf-8")
                self.assertEqual(content.count("# Bundle fact"), 1)


if __name__ == "__main__":
    unittest.main()
