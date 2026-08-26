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
import shutil
import sys
import tempfile
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


if __name__ == "__main__":
    unittest.main(verbosity=2)