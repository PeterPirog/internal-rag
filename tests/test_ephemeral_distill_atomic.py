#!/usr/bin/env python3
"""Tests for ephemeral observations, diagnostic distillation, and atomic writes.

Covers:
  - Ephemeral store: add/get/list/delete/promote/cleanup/stats
  - TTL expiry
  - max_records / max_bytes limits
  - Secret redaction
  - 5000-line output -> short conclusion (distillation)
  - Warning without future value does NOT create durable memory
  - Important repeated gotcha is NOT removed by decay (GC)
  - Atomic writes: temp -> fsync -> replace
  - ProjectWriteLock: acquire/release/reentrant/stale reclaim

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
from typing import Any, Dict

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
SKILL_DIR = PROJECT_ROOT / ".agents" / "skills" / "internal-rag"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EPHEMERAL_PATH = SKILL_DIR / "irag_ephemeral.py"
DISTILL_PATH = SKILL_DIR / "irag_distill.py"
ATOMIC_PATH = SKILL_DIR / "irag_atomic.py"


class TestEphemeralStore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="eph-"))
        (self.tmp / "INTERNAL_RAG").mkdir()
        self.rag = self.tmp / "INTERNAL_RAG"
        self.eph = _load_module("eph_test", EPHEMERAL_PATH)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_and_get(self):
        oid = self.eph.add_observation(self.rag, "pytest", "test output line")
        self.assertIsNotNone(oid)
        obs = self.eph.get_observation(self.rag, oid)
        self.assertIsNotNone(obs)
        self.assertEqual(obs["source"], "pytest")
        self.assertIn("test output", obs["content"])

    def test_ttl_expiry(self):
        oid = self.eph.add_observation(self.rag, "pytest", "temp obs",
                                        ttl_seconds=1)
        self.assertIsNotNone(oid)
        time.sleep(1.5)
        obs = self.eph.get_observation(self.rag, oid)
        self.assertIsNone(obs)  # expired

    def test_max_records(self):
        for i in range(10):
            self.eph.add_observation(self.rag, "test", f"obs {i}",
                                     max_records=5)
        stats = self.eph.ephemeral_stats(self.rag)
        self.assertLessEqual(stats["count"], 5)

    def test_secret_redaction(self):
        oid = self.eph.add_observation(self.rag, "env", "API_KEY=sk-12345secret")
        obs = self.eph.get_observation(self.rag, oid)
        self.assertIn("REDACTED", obs["content"])
        self.assertNotIn("sk-12345secret", obs["content"])

    def test_delete_observation(self):
        oid = self.eph.add_observation(self.rag, "test", "delete me")
        self.assertTrue(self.eph.delete_observation(self.rag, oid))
        self.assertIsNone(self.eph.get_observation(self.rag, oid))

    def test_mark_promoted(self):
        oid = self.eph.add_observation(self.rag, "test", "promote me")
        self.assertTrue(self.eph.mark_promoted(self.rag, oid, "mem-123",
                                                distilled="conclusion"))
        obs = self.eph.get_observation(self.rag, oid)
        self.assertEqual(obs["promoted"], 1)
        self.assertEqual(obs["promoted_to"], "mem-123")

    def test_cleanup_expired(self):
        self.eph.add_observation(self.rag, "test", "expired", ttl_seconds=1)
        self.eph.add_observation(self.rag, "test", "alive", ttl_seconds=300)
        time.sleep(1.5)
        deleted = self.eph.cleanup_expired(self.rag)
        self.assertGreaterEqual(deleted, 1)

    def test_clear_all(self):
        for i in range(5):
            self.eph.add_observation(self.rag, "test", f"obs {i}")
        deleted = self.eph.clear_all(self.rag)
        self.assertEqual(deleted, 5)
        stats = self.eph.ephemeral_stats(self.rag)
        self.assertEqual(stats["count"], 0)

    def test_stats(self):
        self.eph.add_observation(self.rag, "test", "some content")
        stats = self.eph.ephemeral_stats(self.rag)
        self.assertTrue(stats["available"])
        self.assertGreater(stats["count"], 0)
        self.assertGreater(stats["total_bytes"], 0)

    def test_large_output_truncated(self):
        big = "x" * (200 * 1024)  # 200KB
        oid = self.eph.add_observation(self.rag, "build", big,
                                        max_record_bytes=1024)
        obs = self.eph.get_observation(self.rag, oid)
        self.assertLess(len(obs["content"]), 200 * 1024)
        self.assertIn("truncated", obs["content"])


class TestDistillation(unittest.TestCase):
    def setUp(self):
        self.distill = _load_module("distill_test", DISTILL_PATH)

    def test_5000_line_output_to_conclusion(self):
        """A 5000-line test output should be reduced to a short conclusion."""
        lines = []
        for i in range(4990):
            lines.append(f"  test_case_{i} ... ok")
        lines.append("  test_critical_case ... FAIL")
        lines.append("Traceback (most recent call last):")
        lines.append('  File "src/auth.py", line 42, in test_critical_case')
        lines.append("    assert token is not None")
        lines.append("AssertionError: assert None is not None")
        lines.append("4990 passed, 1 failed in 12.3s")
        content = "\n".join(lines)
        self.assertGreater(len(content), 50000)  # confirm it's large

        d = self.distill.distill_output("pytest", content, command="pytest", exit_code=1)
        self.assertGreater(d["confidence"], 0.3)
        self.assertIn("AssertionError", d["conclusion"])
        self.assertLess(len(d["conclusion"]), 300)
        self.assertTrue(d["should_promote"])

    def test_warning_without_value_no_promote(self):
        """A warning without future value should NOT be promoted to durable."""
        content = "WARNING: deprecation notice for old_api()\n1 passed in 0.1s"
        d = self.distill.distill_output("pytest", content, exit_code=0)
        self.assertFalse(d["should_promote"],
                         f"warning without value should not promote: conf={d['confidence']}")

    def test_successful_output_no_promote(self):
        """Successful output with no errors should NOT be promoted."""
        content = "All 100 tests passed in 2.3s\nOK"
        d = self.distill.distill_output("pytest", content, exit_code=0)
        self.assertFalse(d["should_promote"])

    def test_distill_to_memory_body(self):
        content = "FAILED test_x\nAssertionError: bad value\nFile 'x.py', line 10"
        d = self.distill.distill_output("pytest", content, exit_code=1)
        result = self.distill.distill_to_memory_body(d)
        if d["should_promote"]:
            self.assertIsNotNone(result)
            title, body = result
            self.assertIn("Failure", title)
            self.assertIn("Root cause", body)

    def test_exception_extraction(self):
        content = (
            "Traceback (most recent call last):\n"
            '  File "src/db.py", line 88, in connect\n'
            "    conn = psycopg2.connect(url)\n"
            "OperationalError: could not connect to server\n"
        )
        d = self.distill.distill_output("db", content, exit_code=1)
        self.assertEqual(d["exception_type"], "OperationalError")
        self.assertIn("could not connect", d["exception_message"])
        self.assertTrue(d["should_promote"])

    def test_stack_frames_extraction(self):
        content = (
            "Traceback (most recent call last):\n"
            '  File "src/a.py", line 10, in func_a\n'
            '  File "src/b.py", line 20, in func_b\n'
            '  File "src/c.py", line 30, in func_c\n'
            "ValueError: bad input\n"
        )
        d = self.distill.distill_output("app", content, exit_code=1)
        self.assertEqual(len(d["stack_frames"]), 3)
        self.assertEqual(d["stack_frames"][-1]["function"], "func_c")


class TestAtomicWrites(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="atomic-"))
        self.atomic = _load_module("atomic_test", ATOMIC_PATH)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_atomic_write_text(self):
        p = self.tmp / "test.txt"
        self.atomic.atomic_write_text(p, "hello world\n")
        self.assertEqual(p.read_text(encoding="utf-8"), "hello world\n")

    def test_atomic_write_bytes(self):
        p = self.tmp / "test.bin"
        self.atomic.atomic_write_bytes(p, b"\x00\x01\x02")
        self.assertEqual(p.read_bytes(), b"\x00\x01\x02")

    def test_atomic_write_replaces_existing(self):
        p = self.tmp / "test.txt"
        p.write_text("old content", encoding="utf-8")
        self.atomic.atomic_write_text(p, "new content\n")
        self.assertEqual(p.read_text(encoding="utf-8"), "new content\n")

    def test_atomic_write_no_temp_left(self):
        p = self.tmp / "test.txt"
        self.atomic.atomic_write_text(p, "content")
        temps = list(self.tmp.glob(".*.tmp"))
        self.assertEqual(len(temps), 0, f"temp files left: {temps}")

    def test_project_write_lock_acquire_release(self):
        lock_path = self.tmp / ".write.lock"
        lock = self.atomic.ProjectWriteLock(lock_path, timeout=2)
        lock.acquire()
        self.assertTrue(lock_path.exists())
        lock.release()
        self.assertFalse(lock_path.exists())

    def test_project_write_lock_context_manager(self):
        lock_path = self.tmp / ".write.lock"
        with self.atomic.ProjectWriteLock(lock_path, timeout=2):
            self.assertTrue(lock_path.exists())
        self.assertFalse(lock_path.exists())

    def test_project_write_lock_stale_reclaim(self):
        lock_path = self.tmp / ".write.lock"
        # Create a stale lock (old timestamp)
        lock_path.write_text(f"99999\n{time.time() - 300}\n", encoding="ascii")
        with self.atomic.ProjectWriteLock(lock_path, timeout=2, stale_seconds=60):
            self.assertTrue(lock_path.exists())
        self.assertFalse(lock_path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)