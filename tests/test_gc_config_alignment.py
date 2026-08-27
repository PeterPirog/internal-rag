#!/usr/bin/env python3
"""v1.8.1 GC alignment: one canonical policy (gc.*), CLI flags > config,
archive_after_days staging, snapshot byte budget, dry-run zero mutation,
deprecated top-level `snapshots` alias, and _validate_config coverage.

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
IRAG_PATH = SKILL_DIR / "irag.py"
GC_PATH = SKILL_DIR / "irag_gc.py"
EPH_PATH = SKILL_DIR / "irag_ephemeral.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _days_ago(d: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() - d * 86400))


def _make_memory(path: Path, mid: str, mtype: str, created: str) -> Tuple[Path, Dict[str, Any]]:
    fm = {"id": mid, "type": mtype, "status": "active", "created": created,
          "scope": [], "tags": [], "sources": [], "links": []}
    content = (f"---\nid: {mid}\ntype: {mtype}\nstatus: active\ncreated: {created}\n"
               f"scope: []\ntags: []\nsources: []\nlinks: []\n---\n\n# {mid}\n\nbody\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path, fm


def _tree_state(root: Path) -> Dict[str, bytes]:
    """Full directory tree as {relative-path: file-bytes} for mutation checks."""
    out: Dict[str, bytes] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = p.read_bytes()
    return out


class _IragEnv:
    """Temp project with irag module globals redirected (root, RAG, config)."""

    def __init__(self, cfg_text: str = ""):
        self.tmp = Path(tempfile.mkdtemp(prefix="gc-align-"))
        self.rag = self.tmp / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures",
                  "hypotheses", "sessions", "sessions/.snapshots", "archive"):
            (self.rag / d).mkdir(parents=True, exist_ok=True)
        self.config_path = self.tmp / ".irag.yml"
        if cfg_text:
            self.config_path.write_text(cfg_text, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("irag_align_mod", str(IRAG_PATH))
        assert spec is not None
        self.irag = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(self.irag)
        self._saved = (self.irag.ROOT, self.irag.RAG, self.irag.CONFIG_PATH)
        self.irag.ROOT = self.tmp
        self.irag.RAG = self.rag
        self.irag.CONFIG_PATH = self.config_path
        self.gc = _load("gc_align_mod", GC_PATH)
        self.eph = _load("eph_align_mod", EPH_PATH)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.irag.ROOT, self.irag.RAG, self.irag.CONFIG_PATH = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *argv: str) -> Tuple[int, str]:
        import io
        saved = sys.argv
        buf_out, buf_err = io.StringIO(), io.StringIO()
        sys.argv = ["irag.py"] + list(argv)
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = buf_out, buf_err
        try:
            try:
                self.irag.main()
                code = 0
            except SystemExit as e:
                code = int(e.code) if isinstance(e.code, (int, type(None))) else 1
                if e.code is None:
                    code = 0
        finally:
            sys.argv = saved
            sys.stdout, sys.stderr = old_out, old_err
        return code, buf_out.getvalue()


class TestCanonicalConfigShape(unittest.TestCase):
    def test_default_gc_shape(self):
        g = json.loads(json.dumps(_load("gc_shape_mod", IRAG_PATH).DEFAULT_CONFIG))["gc"]
        self.assertEqual(
            sorted(g),
            sorted(["grace_days", "stale_days", "gc_candidate_days",
                    "archive_after_days", "snapshot_max_age_days",
                    "snapshot_max_count", "snapshot_max_bytes"]))
        self.assertEqual(g["archive_after_days"], 365)

    def test_config_file_overrides_gc(self):
        with _IragEnv("gc:\n  stale_days: 11\n  gc_candidate_days: 21\n  archive_after_days: 51\n") as env:
            cfg = env.irag.load_config()
            self.assertEqual(cfg["gc"]["stale_days"], 11)
            self.assertEqual(cfg["gc"]["gc_candidate_days"], 21)
            self.assertEqual(cfg["gc"]["archive_after_days"], 51)
            # sibling defaults retained
            self.assertEqual(cfg["gc"]["grace_days"], 30)
            self.assertEqual(cfg["gc"]["snapshot_max_bytes"], 0)

    def test_top_level_snapshots_deprecated_alias(self):
        with _IragEnv("snapshots:\n  max_age_days: 7\n  max_count: 3\n  max_bytes: 1024\n") as env:
            cfg = env.irag.load_config()
            self.assertEqual(cfg["gc"]["snapshot_max_age_days"], 7)
            self.assertEqual(cfg["gc"]["snapshot_max_count"], 3)
            self.assertEqual(cfg["gc"]["snapshot_max_bytes"], 1024)

    def test_explicit_gc_beats_snapshots_alias(self):
        with _IragEnv("snapshots:\n  max_age_days: 7\ngc:\n  snapshot_max_age_days: 99\n") as env:
            cfg = env.irag.load_config()
            self.assertEqual(cfg["gc"]["snapshot_max_age_days"], 99,
                             "explicit gc.* must win over the deprecated alias")


class TestCliOverridesConfig(unittest.TestCase):
    def test_cli_flag_wins_over_config(self):
        cfg = ("gc:\n  grace_days: 7\n  stale_days: 11\n  gc_candidate_days: 21\n"
               "  archive_after_days: 51\n  snapshot_max_age_days: 7\n"
               "  snapshot_max_count: 3\n  snapshot_max_bytes: 1024\n")
        with _IragEnv(cfg) as env:
            p, _ = _make_memory(env.rag / "sessions" / "old.md", "mem-old",
                                "session", created="2024-01-01")
            code, out = env.run_cli("gc", "--json",
                                    "--grace-days", "1",
                                    "--stale-days", "2",
                                    "--gc-candidate-days", "3",
                                    "--archive-after-days", "4",
                                    "--snapshot-max-age-days", "5",
                                    "--snapshot-max-count", "6",
                                    "--snapshot-max-bytes", "7")
            self.assertEqual(code, 0, out)
            payload = json.loads(out)
            policy = payload["policy"]
            self.assertEqual(policy["grace_days"], 1)
            self.assertEqual(policy["stale_days"], 2)
            self.assertEqual(policy["gc_candidate_days"], 3)
            self.assertEqual(policy["archive_after_days"], 4)
            self.assertEqual(policy["snapshot_max_age_days"], 5)
            self.assertEqual(policy["snapshot_max_count"], 6)
            self.assertEqual(policy["snapshot_max_bytes"], 7)

    def test_without_flags_config_values_used(self):
        cfg = ("gc:\n  grace_days: 7\n  stale_days: 11\n  gc_candidate_days: 21\n"
               "  archive_after_days: 51\n  snapshot_max_age_days: 7\n"
               "  snapshot_max_count: 3\n  snapshot_max_bytes: 1024\n")
        with _IragEnv(cfg) as env:
            _make_memory(env.rag / "sessions" / "old.md", "mem-old",
                         "session", created="2024-01-01")
            code, out = env.run_cli("gc", "--json")
            self.assertEqual(code, 0, out)
            policy = json.loads(out)["policy"]
            self.assertEqual(policy["grace_days"], 7)
            self.assertEqual(policy["stale_days"], 11)
            self.assertEqual(policy["gc_candidate_days"], 21)
            self.assertEqual(policy["archive_after_days"], 51)
            self.assertEqual(policy["snapshot_max_age_days"], 7)
            self.assertEqual(policy["snapshot_max_count"], 3)
            self.assertEqual(policy["snapshot_max_bytes"], 1024)


class TestStaging180vs365(unittest.TestCase):
    """archive_after_days must actually drive staging: it archives regardless
    of value, and gc_candidate_days (180) archives only low-value memories.
    Value scoring itself is unchanged (no redesign)."""

    def setUp(self):
        env = _IragEnv()
        self.env = env
        self.gc = env.gc
        self.irag = env.irag
        self.rag = env.rag

    def tearDown(self):
        self.env.__exit__(None, None, None)

    def _plan(self, **kw) -> Dict[str, Any]:
        files = []
        for p in self.rag.rglob("*.md"):
            if "archive" in p.parts or ".snapshots" in p.parts:
                continue
            text, fm = self.irag._read_memory(p)
            files.append((p, fm))
        return self.gc.gc_plan(self.rag, files, **kw)

    def test_low_value_archives_at_candidate_threshold(self):
        """A low-value (value < 0.3) session past gc_candidate_days=180 is an
        archive candidate — even though archive_after_days is far away.
        Value is pinned deterministically to test the staging branch."""
        _make_memory(self.rag / "sessions" / "low180.md", "mem-180",
                     "session", created=_days_ago(250))
        orig = self.gc._compute_memory_value
        self.gc._compute_memory_value = lambda fm, u, **kw: 0.1  # forced low
        try:
            plan = self._plan(gc_candidate_days=180, archive_after_days=9999)
        finally:
            self.gc._compute_memory_value = orig
        cands = [c for c in plan["candidates"] if c["id"] == "mem-180"]
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["action"], "archive")
        self.assertIn("max_age 180d", cands[0]["reason"])

    def test_low_value_archives_respects_raised_threshold(self):
        """Same low-value memory, but gc_candidate_days=9999 -> NOT archived
        by the candidate branch (proves the threshold value controls it)."""
        _make_memory(self.rag / "sessions" / "low180b.md", "mem-180b",
                     "session", created=_days_ago(250))
        orig = self.gc._compute_memory_value
        self.gc._compute_memory_value = lambda fm, u, **kw: 0.1
        try:
            plan = self._plan(gc_candidate_days=9999, archive_after_days=9999)
        finally:
            self.gc._compute_memory_value = orig
        cands = [c for c in plan["candidates"] if c["id"] == "mem-180b"
                 and c["action"] == "archive"]
        self.assertEqual(cands, [])

    def test_high_value_not_archived_at_candidate_threshold(self):
        """A high-value knowledge memory past 180d stays (value >= 0.3 and
        archive_after_days far away)."""
        p = self.rag / "knowledge" / "highval.md"
        fm = {"id": "mem-hv", "type": "knowledge", "status": "active",
              "created": _days_ago(250), "confidence": "high",
              "scope": [], "tags": [], "sources": [], "links": []}
        content = (f"---\nid: {fm['id']}\ntype: knowledge\nstatus: active\n"
                   f"created: {fm['created']}\nconfidence: high\nscope: []\n"
                   f"tags: []\nsources: []\nlinks: []\n---\n\n# {fm['id']}\n\nbody\n")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        plan = self.gc.gc_plan(self.rag, [(p, fm)],
                               gc_candidate_days=180, archive_after_days=9999)
        archives = [c for c in plan["candidates"] if c["action"] == "archive"]
        self.assertEqual(archives, [],
                         f"high-value memory must not archive at 180d: {plan['candidates']}")

    def test_archive_after_days_stages_high_value(self):
        """archive_after_days=180 stages a HIGH-VALUE memory — proving the
        policy value actually drives staging (value-independent floor)."""
        p = self.rag / "knowledge" / "highval180.md"
        fm = {"id": "mem-hv180", "type": "knowledge", "status": "active",
              "created": _days_ago(250), "confidence": "high",
              "scope": [], "tags": [], "sources": [], "links": []}
        content = (f"---\nid: {fm['id']}\ntype: knowledge\nstatus: active\n"
                   f"created: {fm['created']}\nconfidence: high\nscope: []\n"
                   f"tags: []\nsources: []\nlinks: []\n---\n\n# {fm['id']}\n\nbody\n")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        plan = self.gc.gc_plan(self.rag, [(p, fm)],
                               gc_candidate_days=180, archive_after_days=180)
        cands = [c for c in plan["candidates"] if c["action"] == "archive"]
        self.assertEqual(len(cands), 1,
                         f"archive_after_days must stage this memory: {plan['candidates']}")
        self.assertIn("archive_after_days 180d", cands[0]["reason"])

    def test_400_days_archives_at_365_default(self):
        _make_memory(self.rag / "knowledge" / "old400.md", "mem-400",
                     "knowledge", created=_days_ago(400))
        plan = self._plan(gc_candidate_days=180, archive_after_days=365)
        cands = [c for c in plan["candidates"] if c["id"] == "mem-400"
                 and c["action"] == "archive"]
        self.assertEqual(len(cands), 1)
        self.assertIn("archive_after_days 365d", cands[0]["reason"])

    def test_400_days_not_archived_when_threshold_500(self):
        """age 400d with both thresholds at 500d: no archive (deprioritize
        at most), proving the threshold value controls staging."""
        _make_memory(self.rag / "knowledge" / "old400b.md", "mem-400b",
                     "knowledge", created=_days_ago(400))
        plan = self._plan(gc_candidate_days=500, archive_after_days=500)
        cands = [c for c in plan["candidates"] if c["id"] == "mem-400b"
                 and c["action"] == "archive"]
        self.assertEqual(cands, [],
                         "400d < 500d thresholds must not archive")


class TestSnapshotByteBudget(unittest.TestCase):
    """snapshot_gc_plan must remove the minimal sufficient set and decrement
    the remaining byte budget as files are selected."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="snap-bytes-"))
        self.rag = self.tmp / "INTERNAL_RAG"
        self.snap_dir = self.rag / "sessions" / ".snapshots"
        self.snap_dir.mkdir(parents=True)
        self.gc = _load("gc_bytes_mod", GC_PATH)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _mk(self, name: str, size: int, age_days: int) -> Path:
        p = self.snap_dir / name
        p.write_bytes(b"x" * size)
        t = time.time() - age_days * 86400
        os.utime(p, (t, t))
        return p

    def test_minimal_sufficient_set(self):
        # 6 x 100B = 600B; budget 250B -> must delete exactly 4 (oldest first).
        # s0 = 10d ago (newest, active), s5 = 15d ago (oldest).
        # Deleting oldest-first: s5, s4, s3, s2 -> remaining s0+s1 = 200 <= 250.
        for i in range(6):
            self._mk(f"s{i}.md", 100, 10 + i)
        plan = self.gc.snapshot_gc_plan(self.rag, max_age_days=999,
                                        max_count=99, max_bytes=250)
        self.assertEqual(plan["would_delete"], 4)
        deleted = {Path(c["path"]).name for c in plan["candidates"]}
        self.assertEqual(deleted, {"s2.md", "s3.md", "s4.md", "s5.md"})
        remaining = 600 - 400
        self.assertLessEqual(remaining, 250)

    def test_remaining_fits_after_smaller_set(self):
        # uneven sizes: oldest 200B, others 50B x5 = 450B total; budget 300B.
        # Deleting the 200B oldest alone leaves 250B <= 300B -> only 1 delete.
        self._mk("big.md", 200, 50)
        for i in range(5):
            self._mk(f"s{i}.md", 50, 10 + i)
        plan = self.gc.snapshot_gc_plan(self.rag, max_age_days=999,
                                        max_count=99, max_bytes=300)
        self.assertEqual(plan["would_delete"], 1)
        self.assertEqual(Path(plan["candidates"][0]["path"]).name, "big.md")

    def test_active_recovery_point_never_deleted(self):
        # budget so small that even the active snapshot would 'fit' the math:
        # 3 x 100B, budget 50B -> only 1 may remain, and it must be the active.
        for i in range(3):
            self._mk(f"a{i}.md", 100, 10 + i)
        plan = self.gc.snapshot_gc_plan(self.rag, max_age_days=999,
                                        max_count=99, max_bytes=50)
        active = Path(plan["active_recovery_point"]).name
        deleted = {Path(c["path"]).name for c in plan["candidates"]}
        self.assertNotIn(active, deleted,
                         "active recovery point must never be deleted")
        self.assertEqual(len(deleted), 2)


class TestDryRunZeroMutation(unittest.TestCase):
    """`gc --dry-run` must not modify ANY file or SQLite database."""

    def test_dry_run_zero_mutation(self):
        cfg = "gc:\n  gc_candidate_days: 1\n"
        with _IragEnv(cfg) as env:
            # a stale memory that a real GC WOULD archive
            p, _ = _make_memory(env.rag / "sessions" / "stale.md", "mem-stale",
                                "session", created="2024-01-01")
            # an expired ephemeral observation that a real GC would delete
            oid = env.eph.add_observation(env.rag, "pytest", "will expire",
                                          ttl_seconds=1)
            self.assertIsNotNone(oid)
            time.sleep(1.2)
            # a snapshot that a real GC would delete
            snap = env.rag / "sessions" / ".snapshots" / "old.md"
            snap.write_text("snap\n", encoding="utf-8")
            t = time.time() - 200 * 86400
            os.utime(snap, (t, t))

            before = _tree_state(env.tmp)
            eph_bytes_before = (env.rag / ".ephemeral.db").read_bytes()

            code, out = env.run_cli("gc", "--dry-run", "--json")
            self.assertEqual(code, 0, out)

            after = _tree_state(env.tmp)
            self.assertEqual(before, after,
                             "dry-run must not add/remove/modify any file")
            self.assertEqual((env.rag / ".ephemeral.db").read_bytes(),
                             eph_bytes_before,
                             "dry-run must not modify the ephemeral SQLite DB")
            # the observation is still physically present (not expired-deleted)
            import sqlite3
            conn = sqlite3.connect(str(env.rag / ".ephemeral.db"))
            rows = conn.execute("SELECT id FROM ephemeral_observations "
                                "WHERE id = ?", (oid,)).fetchall()
            conn.close()
            self.assertEqual(len(rows), 1,
                             "dry-run must NOT delete expired observations")
            # and the report is a real plan (it SAW the stale memory)
            payload = json.loads(out)
            self.assertGreaterEqual(payload["plan"]["would_archive"], 1)

    def test_dry_run_keeps_unexpired_observations_readable(self):
        """Dry-run must not delete observations: a LIVE one stays get-able and
        an EXPIRED one stays stored (TTL cleanup is --apply / explicit only)."""
        with _IragEnv() as env:
            live = env.eph.add_observation(env.rag, "pytest", "live obs")
            dead = env.eph.add_observation(env.rag, "pytest", "expired obs",
                                           ttl_seconds=1)
            self.assertIsNotNone(live)
            self.assertIsNotNone(dead)
            time.sleep(1.2)
            eph_bytes_before = (env.rag / ".ephemeral.db").read_bytes()

            code, out = env.run_cli("gc", "--dry-run", "--json")
            self.assertEqual(code, 0, out)

            self.assertTrue((env.rag / ".ephemeral.db").read_bytes()
                            == eph_bytes_before,
                            "dry-run must not modify the ephemeral SQLite DB")
            self.assertIsNotNone(env.eph.get_observation(env.rag, live),
                                 "live observation must survive dry-run")
            # expired row is still physically present (cleanup is --apply only)
            import sqlite3
            conn = sqlite3.connect(str(env.rag / ".ephemeral.db"))
            rows = conn.execute("SELECT id FROM ephemeral_observations "
                                "WHERE id = ?", (dead,)).fetchall()
            conn.close()
            self.assertEqual(len(rows), 1,
                             "dry-run must NOT delete expired observations")

    def test_apply_does_run_ttl_cleanup(self):
        with _IragEnv() as env:
            oid = env.eph.add_observation(env.rag, "pytest", "expires",
                                          ttl_seconds=1)
            self.assertIsNotNone(oid)
            time.sleep(1.2)
            self.assertTrue(env.eph.ephemeral_stats(env.rag)["expired"] >= 1)
            code, out = env.run_cli("gc", "--apply", "--json")
            self.assertEqual(code, 0, out)
            stats = env.eph.ephemeral_stats(env.rag)
            self.assertEqual(stats["count"], 0,
                             "--apply must run ephemeral TTL cleanup")


class TestValidationGcEphemeral(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("irag_val_mod", str(IRAG_PATH))
        assert spec is not None
        self.irag = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(self.irag)

    def test_valid_gc_ephemeral_passes(self):
        cfg = json.loads(json.dumps(self.irag.DEFAULT_CONFIG))
        self.assertEqual(self.irag._validate_config(cfg), [])

    def test_bad_gc_values_flagged(self):
        cfg = json.loads(json.dumps(self.irag.DEFAULT_CONFIG))
        cfg["gc"]["grace_days"] = -1
        cfg["gc"]["archive_after_days"] = "soon"
        cfg["gc"]["snapshot_max_count"] = True
        issues = self.irag._validate_config(cfg)
        self.assertTrue(any("gc.grace_days" in i for i in issues))
        self.assertTrue(any("gc.archive_after_days" in i for i in issues))
        self.assertTrue(any("gc.snapshot_max_count" in i for i in issues))

    def test_bad_ephemeral_values_flagged(self):
        cfg = json.loads(json.dumps(self.irag.DEFAULT_CONFIG))
        cfg["ephemeral"]["ttl_seconds"] = 0
        cfg["ephemeral"]["max_bytes"] = -5
        issues = self.irag._validate_config(cfg)
        self.assertTrue(any("ephemeral.ttl_seconds" in i for i in issues))
        self.assertTrue(any("ephemeral.max_bytes" in i for i in issues))

    def test_deprecated_snapshots_alias_validated(self):
        cfg = json.loads(json.dumps(self.irag.DEFAULT_CONFIG))
        cfg["snapshots"] = {"max_age_days": -3}
        issues = self.irag._validate_config(cfg)
        self.assertTrue(any("snapshots.max_age_days" in i for i in issues))

    def test_gc_not_mapping_flagged(self):
        cfg = json.loads(json.dumps(self.irag.DEFAULT_CONFIG))
        cfg["gc"] = "fast"
        issues = self.irag._validate_config(cfg)
        self.assertTrue(any("gc: must be a mapping" in i for i in issues))


if __name__ == "__main__":
    unittest.main(verbosity=2)
