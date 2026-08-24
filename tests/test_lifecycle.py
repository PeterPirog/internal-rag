#!/usr/bin/env python3
"""Tests for the temporal, safe knowledge lifecycle (schema-2 frontmatter).

Covers:
- knowledge update A -> B preserves A historically (supersede, not delete)
- `search --at` before the change finds A; after the change B is preferred
- unknown dates do not raise
- schema-1 import still works (no schema-2 fields present)
- `consolidate --dry-run` is deterministic and read-only
- timeline sorts by effective validity (valid_from/created), not filename
"""
from __future__ import annotations
import importlib.util
import io
import json
import re
import time
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
IRAG_PATH = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag.py"

_spec = importlib.util.spec_from_file_location("irag_mod", str(IRAG_PATH))
irag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(irag)


class Env:
    def __init__(self, sandbox: Path):
        self.sandbox = sandbox
        self.rag = sandbox / "INTERNAL_RAG"
        for d in ["decisions", "knowledge", "gotchas", "failures", "hypotheses", "sessions", "archive",
                  "sessions/.snapshots"]:
            (self.rag / d).mkdir(parents=True, exist_ok=True)
        (self.rag / "WORKING_STATE.md").write_text("# Working state\n", encoding="utf-8")

    def __enter__(self):
        self._old = (irag.ROOT, irag.RAG, irag.CONFIG_PATH, irag.WORKING)
        irag.ROOT = self.sandbox
        irag.RAG = self.rag
        irag.CONFIG_PATH = self.sandbox / ".irag.yml"
        irag.WORKING = self.rag / "WORKING_STATE.md"
        irag._open_sqlite_index = lambda: None
        irag._embed_cache = {}
        return self

    def __exit__(self, *a):
        irag.ROOT, irag.RAG, irag.CONFIG_PATH, irag.WORKING = self._old
        irag._embed_cache = {}

    def write_memory(self, subdir: str, name: str, mtype: str, title: str, body: str,
                     status: str = "active", extra: str = "", created: str = "2024-01-01") -> Path:
        p = self.rag / subdir / name
        fm = (f"---\nid: mem-{name.replace('.md','')}\ntype: {mtype}\nstatus: {status}\n"
              f"created: {created}\nscope: []\ntags: []\n{extra}---\n\n# {title}\n\n"
              f"## Knowledge\n\n{body}\n\n## Consequence\n\nNone.\n")
        p.write_text(fm, encoding="utf-8")
        return p


def _class(**kw):
    class C: pass
    for k, v in kw.items():
        setattr(C, k, v)
    return C()


class AtoBHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = PROJECT_ROOT / "_tmp_lifecycle_a2b"
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.env = Env(self.tmp)
        self.env.__enter__()

    def tearDown(self):
        self.env.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_update_a_to_b_preserves_a(self):
        old = self.env.write_memory("decisions", "0001-a.md", "decision", "Auth uses Basic",
                                    "Authentication uses Basic over HTTP for all endpoints.",
                                    created="2023-01-01")
        new = self.env.write_memory("decisions", "0002-b.md", "decision", "Auth uses JWT",
                                    "Authentication uses JWT tokens with refresh rotation for all endpoints.",
                                    created="2023-06-01")
        # A -> B: B replaces A
        args = _class(ref=str(old.relative_to(irag.ROOT)), by=str(new.relative_to(irag.ROOT)),
                      reason="migrated to tokens", valid_to=None, force=False)
        with redirect_stdout(io.StringIO()):
            rc = irag.supersede(args)
        self.assertEqual(rc, 0)
        old_fm = irag.parse_fm(old.read_text(encoding="utf-8"))
        new_fm = irag.parse_fm(new.read_text(encoding="utf-8"))
        # A is preserved, not deleted
        self.assertTrue(old.exists())
        self.assertEqual(old_fm["status"], "superseded")
        self.assertIn("mem-0002-b", str(old_fm.get("superseded_by", "")))
        self.assertTrue(old_fm.get("valid_to"))
        self.assertIn("mem-0001-a", new_fm.get("supersedes", []))
        # body of A is intact
        self.assertIn("Basic over HTTP", old.read_text(encoding="utf-8"))


class SearchAt(unittest.TestCase):
    def setUp(self):
        self.tmp = PROJECT_ROOT / "_tmp_lifecycle_at"
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.env = Env(self.tmp)
        self.env.__enter__()
        # A: valid until 2023-05-31, superseded by B
        self.a = self.env.write_memory("decisions", "0001-a.md", "decision", "Auth uses Basic",
                                       "Authentication uses Basic over HTTP for all endpoints.",
                                       extra="valid_to: 2023-05-31\nstatus: superseded\nsuperseded_by: mem-0002-b\n",
                                       created="2023-01-01")
        self.b = self.env.write_memory("decisions", "0002-b.md", "decision", "Auth uses JWT",
                                       "Authentication uses JWT tokens with refresh rotation for all endpoints.",
                                       extra="valid_from: 2023-06-01\nsupersedes:\n  - mem-0001-a\n",
                                       created="2023-06-01")

    def tearDown(self):
        self.env.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, at: str):
        # Mirror the CLI pipeline: temporal-aware retrieval, then post-filter
        # to only memories valid at that date.
        r = irag.search("authentication endpoints", 5, types=None, statuses=None,
                        explain=False, at_date=at)
        return irag._filter_by_date(r, at)

    def test_at_before_change_finds_a(self):
        r = self._run("2023-03-15")
        paths = [str(p.relative_to(irag.ROOT)) for _, p, _, _ in r]
        self.assertTrue(any("0001-a" in x for x in paths), f"A should be valid 2023-03-15, got {paths}")
        self.assertFalse(any("0002-b" in x for x in paths), "B was not yet valid in 2023-03-15")

    def test_at_after_change_prefers_b(self):
        r = self._run("2023-07-15")
        paths = [str(p.relative_to(irag.ROOT)) for _, p, _, _ in r]
        self.assertTrue(any("0002-b" in x for x in paths), f"B should be found, got {paths}")
        self.assertFalse(any("0001-a" in x for x in paths), "A valid_to=2023-05-31 must be excluded")

    def test_unknown_date_no_exception(self):
        for bad in ("not-a-date", "2023-13-99", "", "15/07/2023"):
            r = self._run(bad)
            self.assertIsInstance(r, list)


class Schema1Compat(unittest.TestCase):
    def setUp(self):
        self.tmp = PROJECT_ROOT / "_tmp_lifecycle_s1"
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.env = Env(self.tmp)
        self.env.__enter__()

    def tearDown(self):
        self.env.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_schema1_memory_still_searchable_and_importable(self):
        p = self.env.write_memory("knowledge", "0001-s1.md", "knowledge", "SQLite schema",
                                  "The SQLite index uses schema v3 with a chunks table.",
                                  created="2022-01-01")
        # No schema-2 fields at all: parse/search/validate must not break
        fm = irag.parse_fm(p.read_text(encoding="utf-8"))
        self.assertNotIn("confidence", fm)
        r = irag.search("sqlite index schema", 3, types=None, statuses=None, explain=False)
        self.assertTrue(r)
        # import roundtrip of a schema-1 bundle
        bundle = {"schema": 1, "memories": [{"path": "INTERNAL_RAG/knowledge/0001-s1.md",
                                             "content": p.read_text(encoding="utf-8")}]}
        f = self.tmp / "bundle.json"
        f.write_text(json.dumps(bundle), encoding="utf-8")
        args = _class(file=str(f), overwrite=True, force=False)
        with redirect_stdout(io.StringIO()):
            rc = irag.import_cmd(args)
        self.assertEqual(rc, 0)
        txt = p.read_text(encoding="utf-8").lower()
        self.assertIn("sqlite schema", txt)
        self.assertIn("schema v3", txt)


class ConsolidateDryRun(unittest.TestCase):
    def setUp(self):
        self.tmp = PROJECT_ROOT / "_tmp_lifecycle_consolidate"
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.env = Env(self.tmp)
        self.env.__enter__()
        old = self.env.write_memory("decisions", "0001-a.md", "decision", "Cache TTL",
                                    "The cache TTL is 300 seconds for all API responses.",
                                    created="2022-01-01")
        new = self.env.write_memory("decisions", "0002-b.md", "decision", "Cache TTL",
                                    "The cache TTL is 300 seconds for all API responses.",
                                    created="2022-01-02")
        # Make A superseded by B
        args = _class(ref=str(old.relative_to(irag.ROOT)), by=str(new.relative_to(irag.ROOT)),
                      reason=None, valid_to=None, force=False)
        with redirect_stdout(io.StringIO()):
            irag.supersede(args)
        # old never-accessed entry
        self.env.write_memory("knowledge", "0003-old.md", "knowledge", "Legacy note",
                              "Legacy endpoint note from a retired service.",
                              created="2020-01-01")
        # archived entry
        (self.env.rag / "archive" / "0004-arch.md").write_text(
            "---\nid: mem-0004-arch\ntype: knowledge\nstatus: archived\ncreated: 2020-01-01\n"
            "scope: []\ntags: []\n---\n\n# Archived\n\n## Knowledge\n\nOld text.\n\n## Consequence\n\nNone.\n",
            encoding="utf-8")
        # old session snapshot
        snap = self.env.rag / "sessions" / ".snapshots" / "2020-01-01-snap.md"
        snap.write_text("# snapshot\n", encoding="utf-8")
        old_mtime = time.time() - 45 * 86400
        import os
        os.utime(snap, (old_mtime, old_mtime))

    def tearDown(self):
        self.env.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self):
        args = _class(json=True, dry_run=True, never_accessed_days=90, snapshot_age_days=30)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = irag.consolidate_cmd(args)
        return rc, json.loads(buf.getvalue())

    def test_report_shape(self):
        rc, rep = self._run()
        self.assertEqual(rc, 0)
        cats = {i["category"] for i in rep["issues"]}
        self.assertIn("duplicates", cats)
        self.assertIn("superseded", cats)
        self.assertIn("archived", cats)
        self.assertIn("never_accessed_old", cats)
        self.assertIn("old_snapshots", cats)
        self.assertIsInstance(rep.get("plan"), list)
        self.assertTrue(rep["dry_run"] is True)

    def test_deterministic_and_readonly(self):
        before = {}
        for p in self.env.rag.rglob("*.md"):
            before[str(p)] = (p.read_text(encoding="utf-8"), p.stat().st_mtime_ns)
        rc1, rep1 = self._run()
        rc2, rep2 = self._run()
        self.assertEqual(rc1, 0)
        self.assertEqual(json.dumps(rep1, sort_keys=True), json.dumps(rep2, sort_keys=True))
        after = {}
        for p in self.env.rag.rglob("*.md"):
            after[str(p)] = (p.read_text(encoding="utf-8"), p.stat().st_mtime_ns)
        self.assertEqual(set(before), set(after), "consolidate must not create/delete files")
        for k in before:
            self.assertEqual(before[k][0], after[k][0], f"consolidate must not modify {k}")


class TimelineEffectiveValidity(unittest.TestCase):
    def setUp(self):
        self.tmp = PROJECT_ROOT / "_tmp_lifecycle_timeline"
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.env = Env(self.tmp)
        self.env.__enter__()
        # created early, but valid_from late -> must sort LAST by effective validity
        self.env.write_memory("knowledge", "a-early-created.md", "knowledge", "Early created",
                              "Created early but effective validity is late.",
                              created="2020-01-01", extra="valid_from: 2023-01-01\n")
        # created late, but valid_from early -> must sort FIRST
        self.env.write_memory("knowledge", "b-late-created.md", "knowledge", "Late created",
                              "Created late but effective validity is early.",
                              created="2023-06-01", extra="valid_from: 2020-01-01\n")

    def tearDown(self):
        self.env.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sort_by_effective_validity(self):
        args = _class(limit=0, json=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = irag.timeline(args)
        self.assertEqual(rc, 0)
        items = json.loads(buf.getvalue())
        paths = [i["path"] for i in items]
        self.assertTrue(any("b-late-created" in p for p in paths))
        self.assertTrue(any("a-early-created" in p for p in paths))
        self.assertLess(paths.index(next(p for p in paths if "b-late-created" in p)),
                        paths.index(next(p for p in paths if "a-early-created" in p)))


class RememberSchema2Fields(unittest.TestCase):
    def setUp(self):
        self.tmp = PROJECT_ROOT / "_tmp_lifecycle_remember"
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.env = Env(self.tmp)
        self.env.__enter__()

    def tearDown(self):
        self.env.__exit__(None, None, None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_remember_writes_schema2_fields(self):
        args = _class(type="knowledge", status="active", title="Schema2 field test",
                      scope="", tags="", evidence="", body="A deterministic body for schema two.",
                      consequence="", links="", force=True, allow_secret=True, json=False,
                      confidence="medium", valid_from="2024-01-01", valid_to="2025-01-01",
                      supersedes="mem-old-1,mem-old-2", derived_from="mem-src-1")
        buf = io.StringIO()
        with redirect_stdout(buf):
            res = irag.remember(args)
        self.assertEqual(res, "created")
        files = list((self.env.rag / "knowledge").glob("*.md"))
        self.assertEqual(len(files), 1)
        fm = irag.parse_fm(files[0].read_text(encoding="utf-8"))
        self.assertEqual(fm.get("confidence"), "medium")
        self.assertEqual(fm.get("valid_from"), "2024-01-01")
        self.assertEqual(fm.get("valid_to"), "2025-01-01")
        self.assertEqual(fm.get("supersedes"), ["mem-old-1", "mem-old-2"])
        self.assertEqual(fm.get("derived_from"), ["mem-src-1"])

    def test_validate_rejects_bad_confidence_and_date(self):
        self.env.write_memory("knowledge", "bad.md", "knowledge", "Bad",
                              "Body text here.", extra="confidence: very-high\nvalid_from: 2023-99-99\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = irag.validate()
        out = buf.getvalue()
        self.assertEqual(rc, 1)
        self.assertIn("confidence", out)
        self.assertIn("valid_from", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
