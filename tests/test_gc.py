#!/usr/bin/env python3
"""Tests for GC, retention, snapshot cleanup, and value-aware forgetting.

Covers:
  - GC plan (dry-run): protected decisions/constraints NOT deleted
  - GC: stale low-value memory -> archive candidate
  - GC: archived memory past grace -> delete candidate
  - GC --apply archives and deletes correctly
  - Important repeated gotcha NOT removed by decay
  - Snapshot GC: old snapshots deleted, active recovery point preserved
  - Value-aware memory score computation

Zero external dependencies. Python 3.8+ stdlib only.
"""
from __future__ import annotations
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
SKILL_DIR = PROJECT_ROOT / ".agents" / "skills" / "internal-rag"
GC_PATH = SKILL_DIR / "irag_gc.py"


def _load_gc():
    spec = importlib.util.spec_from_file_location("gc_test", str(GC_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_memory(path: Path, mid: str, mtype: str, status: str = "active",
                 created: str = "2024-01-01", confidence: str = "",
                 links: list = None, tags: list = None) -> Tuple[Path, Dict[str, Any]]:
    """Create a memory file and return (path, frontmatter)."""
    fm: Dict[str, Any] = {
        "id": mid, "type": mtype, "status": status,
        "created": created, "scope": [], "tags": tags or [],
        "sources": [], "links": links or [],
    }
    if confidence:
        fm["confidence"] = confidence
    content = f"---\nid: {mid}\ntype: {mtype}\nstatus: {status}\ncreated: {created}\nscope: []\ntags: {tags or []}\nsources: []\nlinks: {links or []}\n---\n\n# {mid}\n\n## Knowledge\n\ntest content\n"
    path.write_text(content, encoding="utf-8")
    return path, fm


class TestGCPlan(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gc-"))
        self.rag = self.tmp / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures",
                  "hypotheses", "sessions", "sessions/.snapshots", "archive"):
            (self.rag / d).mkdir(parents=True, exist_ok=True)
        self.gc = _load_gc()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_protected_decision_not_in_candidates(self):
        """Active decisions must NEVER be GC candidates."""
        p, fm = _make_memory(self.rag / "decisions" / "arch.md", "mem-arch",
                              "decision", status="active")
        plan = self.gc.gc_plan(self.rag, [(p, fm)])
        self.assertEqual(plan["protected_count"], 1)
        self.assertEqual(len(plan["candidates"]), 0)

    def test_protected_constraint_not_in_candidates(self):
        p, fm = _make_memory(self.rag / "knowledge" / "constraint.md",
                              "mem-const", "constraint", status="active")
        plan = self.gc.gc_plan(self.rag, [(p, fm)])
        self.assertEqual(plan["protected_count"], 1)
        self.assertEqual(len(plan["candidates"]), 0)

    def test_stale_low_value_memory_is_archive_candidate(self):
        # A 200-day-old session memory with no access
        p, fm = _make_memory(self.rag / "sessions" / "old.md", "mem-old",
                              "session", status="active", created="2024-01-01")
        plan = self.gc.gc_plan(self.rag, [(p, fm)], gc_candidate_days=180)
        candidates = [c for c in plan["candidates"] if c["action"] == "archive"]
        self.assertGreater(len(candidates), 0, "stale low-value should be archive candidate")

    def test_archived_past_grace_is_delete_candidate(self):
        p, fm = _make_memory(self.rag / "knowledge" / "old_archived.md",
                              "mem-arch2", "knowledge", status="archived",
                              created="2023-01-01")
        fm["archived_at"] = "2023-06-01"
        plan = self.gc.gc_plan(self.rag, [(p, fm)], grace_days=30)
        candidates = [c for c in plan["candidates"] if c["action"] == "delete"]
        self.assertGreater(len(candidates), 0, "archived past grace should be delete candidate")

    def test_important_gotcha_not_removed_by_decay(self):
        """A frequently-accessed gotcha should NOT be a GC candidate."""
        p, fm = _make_memory(self.rag / "gotchas" / "important.md",
                              "mem-gotcha", "gotcha", status="active",
                              created="2024-01-01", confidence="high")
        # Simulate frequent access
        usage = {"mem-gotcha": {"last_accessed": time.time(), "access_count": 15}}
        # Monkey-patch _load_usage
        orig = self.gc._load_usage
        self.gc._load_usage = lambda r: usage
        try:
            plan = self.gc.gc_plan(self.rag, [(p, fm)])
            candidates = [c for c in plan["candidates"] if c["id"] == "mem-gotcha"]
            self.assertEqual(len(candidates), 0,
                             f"important gotcha should NOT be GC candidate: {candidates}")
        finally:
            self.gc._load_usage = orig

    def test_gc_apply_archives(self):
        p, fm = _make_memory(self.rag / "sessions" / "old2.md", "mem-old2",
                              "session", status="active", created="2024-01-01")
        plan = self.gc.gc_plan(self.rag, [(p, fm)], gc_candidate_days=1)
        result = self.gc.gc_run(self.rag, plan, apply=True)
        self.assertGreater(result["archived"], 0)
        self.assertFalse(p.exists(), "original file should be moved to archive")
        self.assertTrue((self.rag / "archive" / "old2.md").exists())

    def test_gc_dry_run_does_not_modify(self):
        p, fm = _make_memory(self.rag / "sessions" / "old3.md", "mem-old3",
                              "session", status="active", created="2024-01-01")
        plan = self.gc.gc_plan(self.rag, [(p, fm)], gc_candidate_days=1)
        result = self.gc.gc_run(self.rag, plan, apply=False)
        self.assertTrue(p.exists(), "dry-run should not move files")
        self.assertEqual(result["applied"], False)


class TestSnapshotGC(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="snap-gc-"))
        self.rag = self.tmp / "INTERNAL_RAG"
        snap_dir = self.rag / "sessions" / ".snapshots"
        snap_dir.mkdir(parents=True)
        self.gc = _load_gc()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_old_snapshots_deleted(self):
        snap_dir = self.rag / "sessions" / ".snapshots"
        # Create 5 snapshots, 3 old, 2 recent
        for i in range(5):
            p = snap_dir / f"snap{i}.md"
            p.write_text(f"snapshot {i}\n", encoding="utf-8")
            old_time = time.time() - (100 - i * 10) * 86400  # days to seconds
            os.utime(p, (old_time, old_time))
        plan = self.gc.snapshot_gc_plan(self.rag, max_age_days=50, max_count=10)
        self.assertGreater(plan["would_delete"], 0)
        # The most recent (snap4) should be the active recovery point
        self.assertIn("snap4.md", plan["active_recovery_point"])

    def test_active_recovery_point_preserved(self):
        snap_dir = self.rag / "sessions" / ".snapshots"
        for i in range(10):
            p = snap_dir / f"snap{i}.md"
            p.write_text(f"snapshot {i}\n", encoding="utf-8")
            old_time = time.time() - (200 - i * 20)  # decreasing age
            os.utime(p, (old_time, old_time))
        plan = self.gc.snapshot_gc_plan(self.rag, max_age_days=50, max_count=3)
        # The active (most recent) should not be in candidates
        candidates_paths = [c["path"] for c in plan["candidates"]]
        active = Path(plan["active_recovery_point"]).name
        for cp in candidates_paths:
            self.assertNotEqual(Path(cp).name, active,
                                "active recovery point must NOT be a delete candidate")

    def test_max_count_enforced(self):
        snap_dir = self.rag / "sessions" / ".snapshots"
        for i in range(10):
            p = snap_dir / f"snap{i}.md"
            p.write_text(f"s\n", encoding="utf-8")
            t = time.time() - i * 10 * 86400  # days to seconds
            os.utime(p, (t, t))
        plan = self.gc.snapshot_gc_plan(self.rag, max_age_days=999, max_count=3)
        # Should delete all but the 3 most recent
        self.assertEqual(plan["would_delete"], 7)

    def test_snapshot_gc_apply(self):
        snap_dir = self.rag / "sessions" / ".snapshots"
        for i in range(5):
            p = snap_dir / f"snap{i}.md"
            p.write_text(f"s\n", encoding="utf-8")
            t = time.time() - (100 - i * 10) * 86400
            os.utime(p, (t, t))
        plan = self.gc.snapshot_gc_plan(self.rag, max_age_days=50, max_count=10)
        result = self.gc.snapshot_gc_run(plan, apply=True)
        self.assertGreater(result["deleted"], 0)
        # Active should still exist
        active = Path(plan["active_recovery_point"])
        self.assertTrue(active.exists(), "active recovery point must survive GC")


class TestMemoryValueScore(unittest.TestCase):
    def setUp(self):
        self.gc = _load_gc()

    def test_decision_high_confidence_high_value(self):
        fm = {"type": "decision", "status": "active", "created": "2024-01-01",
              "confidence": "high", "links": ["a", "b"]}
        v = self.gc._compute_memory_value(fm, {"last_accessed": time.time(), "access_count": 5})
        self.assertGreater(v, 0.7)

    def test_session_low_value(self):
        fm = {"type": "session", "status": "active", "created": "2023-01-01"}
        v = self.gc._compute_memory_value(fm, {}, now_ts=time.time())
        self.assertLess(v, 0.3)

    def test_superseded_negative_status_modifier(self):
        fm = {"type": "knowledge", "status": "superseded", "created": "2024-01-01"}
        v = self.gc._compute_memory_value(fm, {})
        self.assertLess(v, 0.3)  # superseded heavily penalized


class TestParseTs(unittest.TestCase):
    """P10: last_accessed is stored as an ISO DATE string by irag_index
    (record_access writes date.today().isoformat()) — GC must parse it,
    not crash on float() and treat everything as age 999 days."""

    def setUp(self):
        self.gc = _load_gc()

    def test_iso_date_string(self):
        ts = self.gc._parse_ts("2026-01-15")
        self.assertIsNotNone(ts, "ISO date string must be parseable")
        self.assertGreater(ts, 1_700_000_000)

    def test_iso_datetime_with_z(self):
        ts = self.gc._parse_ts("2026-01-15T10:30:00Z")
        self.assertIsNotNone(ts)

    def test_epoch_float(self):
        self.assertAlmostEqual(self.gc._parse_ts(1750000000.0), 1750000000.0)

    def test_numeric_string(self):
        self.assertAlmostEqual(self.gc._parse_ts("1750000000"), 1750000000.0)

    def test_none_and_garbage(self):
        self.assertIsNone(self.gc._parse_ts(None))
        self.assertIsNone(self.gc._parse_ts(""))
        self.assertIsNone(self.gc._parse_ts("not-a-date"))

    def test_gc_plan_uses_iso_date_last_accessed(self):
        """A memory last accessed via ISO date string is NOT age-999."""
        self.tmp = Path(tempfile.mkdtemp(prefix="gc-ist-"))
        self.rag = self.tmp / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures",
                  "hypotheses", "sessions", "archive"):
            (self.rag / d).mkdir(parents=True, exist_ok=True)
        recent = time.strftime("%Y-%m-%d", time.gmtime())
        usage = {"mem-fresh": {"last_accessed": recent, "access_count": 3}}
        self.gc._load_usage = lambda r: usage
        try:
            p, fm = _make_memory(self.rag / "gotchas" / "fresh.md", "mem-fresh",
                                 "gotcha", status="active",
                                 created=time.strftime("%Y-%m-%d", time.gmtime()))
            plan = self.gc.gc_plan(self.rag, [(p, fm)])
            cands = [c for c in plan["candidates"] if c["id"] == "mem-fresh"]
            self.assertEqual(len(cands), 0,
                             f"recently accessed memory wrongly stale: {cands}")
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)


class TestGcRunMetadataAndLocks(unittest.TestCase):
    """P11/P14/P15: archive stamps archived_at+status BEFORE moving;
    deprioritize writes a real frontmatter marker; ProjectWriteLock wraps
    all mutations; no cross-OS assumption (tempfile dir)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gc-run-"))
        self.rag = self.tmp / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures",
                  "hypotheses", "sessions", "archive"):
            (self.rag / d).mkdir(parents=True, exist_ok=True)
        self.gc = _load_gc()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_archive_stamps_metadata(self):
        p, fm = _make_memory(self.rag / "sessions" / "stale.md", "mem-stale",
                             "session", status="active", created="2024-01-01")
        plan = self.gc.gc_plan(self.rag, [(p, fm)], gc_candidate_days=1)
        result = self.gc.gc_run(self.rag, plan, apply=True)
        self.assertGreater(result["archived"], 0)
        dst = self.rag / "archive" / "stale.md"
        self.assertTrue(dst.exists())
        text = dst.read_text(encoding="utf-8")
        self.assertIn("archived_at:", text, "archived_at must be stamped on archive")
        self.assertTrue(
            re.search(r"^status: archived\s*$", text, re.MULTILINE),
            f"status: archived missing in: {text!r}")

    def test_deprioritize_sets_priority_low(self):
        p, fm = _make_memory(self.rag / "knowledge" / "stale.md", "mem-prio",
                             "knowledge", status="active", created="2024-01-01")
        plan = {"candidates": [{"path": str(p), "id": "mem-prio", "action": "deprioritize"}]}
        result = self.gc.gc_run(self.rag, plan, apply=True)
        self.assertEqual(result["deprioritized"], 1)
        text = p.read_text(encoding="utf-8")
        self.assertIn("priority: low", text, "deprioritize must set priority: low")
        self.assertTrue(p.exists(), "depriorize must NOT move/delete the file")

    def test_deprioritize_dry_run_no_change(self):
        p, fm = _make_memory(self.rag / "knowledge" / "stale.md", "mem-prio2",
                             "knowledge", status="active", created="2024-01-01")
        before = p.read_text(encoding="utf-8")
        plan = {"candidates": [{"path": str(p), "id": "mem-prio2", "action": "deprioritize"}]}
        result = self.gc.gc_run(self.rag, plan, apply=False)
        self.assertEqual(p.read_text(encoding="utf-8"), before)
        self.assertEqual(result["applied"], False)

    def test_project_write_lock_serializes_mutations(self):
        # Two threads must not corrupt the same file: each does an
        # atomic deprioritize round-trip; final content must be coherent.
        p, fm = _make_memory(self.rag / "knowledge" / "race.md", "mem-race",
                             "knowledge", status="active", created="2024-01-01")
        lock_path = self.rag / ".write.lock"
        spec = importlib.util.spec_from_file_location(
            "irag_atomic_test", str(SKILL_DIR / "irag_atomic.py"))
        assert spec is not None
        atomic_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(atomic_mod)
        ProjectWriteLock = atomic_mod.ProjectWriteLock
        errors = []

        def worker(i):
            try:
                for _ in range(20):
                    with ProjectWriteLock(lock_path, timeout=10, stale_seconds=120,
                                          poll_interval=0.01):
                        text = p.read_text(encoding="utf-8")
                        text = self.gc._set_fm_field(text, "priority", "low")
                        atomic_mod.atomic_write_text(p, text, encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                errors.append(f"{i}: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        text = p.read_text(encoding="utf-8")
        # Exactly one `priority:` line, and the file is valid frontmatter
        self.assertEqual(len(re.findall(r"^priority:", text, re.MULTILINE)), 1)
        self.assertIn("priority: low", text)

    def test_delete_past_grace(self):
        p, fm = _make_memory(self.rag / "archive" / "old.md", "mem-old",
                             "knowledge", status="archived", created="2023-01-01")
        plan = {"candidates": [{"path": str(p), "id": "mem-old", "action": "delete"}]}
        result = self.gc.gc_run(self.rag, plan, apply=True)
        self.assertEqual(result["deleted"], 1)
        self.assertFalse(p.exists())


class TestRetrievalPriorityLow(unittest.TestCase):
    """P15: a deprioritized memory must rank lower in search."""

    def setUp(self):
        import sys as _sys
        spec = importlib.util.spec_from_file_location("irag_mod", str(SKILL_DIR / "irag.py"))
        self.irag = importlib.util.module_from_spec(spec)
        _sys.modules["irag_mod"] = self.irag
        spec.loader.exec_module(self.irag)
        self.tmp = Path(tempfile.mkdtemp(prefix="prio-"))
        self.rag = self.tmp / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures",
                  "hypotheses", "sessions", "archive"):
            (self.rag / d).mkdir(parents=True, exist_ok=True)
        self._orig = (self.irag.ROOT, self.irag.RAG)
        self.irag.ROOT = self.tmp
        self.irag.RAG = self.rag

    def tearDown(self):
        self.irag.ROOT, self.irag.RAG = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_priority_low_reduces_boost(self):
        base = {"type": "knowledge", "status": "active", "created": "2026-01-01"}
        normal = self.irag._policy_boost(dict(base))
        low = self.irag._policy_boost(dict(base, priority="low"))
        self.assertLess(low, normal, "priority: low must reduce retrieval rank")
        self.assertAlmostEqual(normal - low, 2.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)