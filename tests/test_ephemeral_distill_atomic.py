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

    # ------------------------------------------------------------------ #
    # Store identity: stable .ephemeral.db (not .index.sqlite3)          #
    # ------------------------------------------------------------------ #

    def test_observe_before_index_then_index_rebuild(self):
        """observe before .index exists -> create index -> observation still
        get/promote-able (stable .ephemeral.db, not the retrieval index)."""
        oid = self.eph.add_observation(self.rag, "pytest", "stable identity test")
        self.assertIsNotNone(oid)
        # No .index.sqlite3 should exist yet.
        self.assertFalse((self.rag / ".index.sqlite3").exists(),
                         "ephemeral must NOT use .index.sqlite3")
        self.assertTrue((self.rag / ".ephemeral.db").exists(),
                        "ephemeral must use .ephemeral.db")
        # Simulate `index --rebuild` creating the retrieval index.
        (self.rag / ".index.sqlite3").write_bytes(b"")
        # The observation must still be get-able from .ephemeral.db.
        obs = self.eph.get_observation(self.rag, oid)
        self.assertIsNotNone(obs, "observation must survive index --rebuild")
        self.assertEqual(obs["source"], "pytest")
        self.assertIn("stable identity", obs["content"])

    def test_ephemeral_db_path_is_stable(self):
        """_ephemeral_db_path always returns .ephemeral.db, regardless of
        whether .index.sqlite3 exists."""
        p_no_index = self.eph._ephemeral_db_path(self.rag)
        self.assertEqual(p_no_index.name, ".ephemeral.db")
        (self.rag / ".index.sqlite3").write_bytes(b"")
        p_with_index = self.eph._ephemeral_db_path(self.rag)
        self.assertEqual(p_with_index.name, ".ephemeral.db",
                         "must NOT switch to .index.sqlite3 when it appears")

    # ------------------------------------------------------------------ #
    # Hard max_bytes: evict oldest until SUM <= max_bytes                #
    # ------------------------------------------------------------------ #

    def test_max_bytes_hard_cap_evicts_more_than_50(self):
        """Over 50 records requiring eviction -> total bytes <= max_bytes.
        The old fixed-50 eviction would leave bytes > max_bytes when many
        small records exceeded the cap. The hard cap must evict ALL oldest
        rows until SUM(content_bytes) <= max_bytes."""
        # 100 records of ~200 bytes each = ~20KB total. Set max_bytes=2000
        # so most must be evicted (far more than 50).
        for i in range(100):
            self.eph.add_observation(self.rag, "test",
                                      f"obs number {i} with some padding content here",
                                      max_bytes=2000, max_records=200)
        stats = self.eph.ephemeral_stats(self.rag)
        self.assertLessEqual(stats["total_bytes"], 2000,
                             f"hard cap must hold: {stats['total_bytes']} > 2000")
        self.assertGreater(stats["count"], 0,
                           "at least the newest record must survive")

    def test_max_bytes_single_record_exceeding_cap(self):
        """A single record larger than max_bytes must be evicted (table ends
        empty or with only the redaction marker)."""
        self.eph.add_observation(self.rag, "test", "x" * 5000,
                                  max_bytes=100, max_records=10)
        stats = self.eph.ephemeral_stats(self.rag)
        self.assertLessEqual(stats["total_bytes"], 100,
                             f"single oversized record must be evicted: {stats}")

    # ------------------------------------------------------------------ #
    # Byte-safe UTF-8 truncation                                          #
    # ------------------------------------------------------------------ #

    def test_multibyte_utf8_truncation(self):
        """Truncation must not split a multibyte UTF-8 sequence (no
        UnicodeDecodeError / mojibake)."""
        # Japanese: each char is 3 bytes in UTF-8. 200 chars = 600 bytes.
        big = "あ" * 200  # 600 bytes
        oid = self.eph.add_observation(self.rag, "test", big,
                                        max_record_bytes=100)
        obs = self.eph.get_observation(self.rag, oid)
        self.assertIsNotNone(obs)
        # Content must be valid UTF-8 (no mojibake) and truncated.
        self.assertLess(len(obs["content"].encode("utf-8")), 100 + 100)
        self.assertIn("truncated", obs["content"])
        # Decoding the stored content must not raise.
        obs["content"].encode("utf-8").decode("utf-8")

    # ------------------------------------------------------------------ #
    # Privacy: secrets redacted BEFORE storage                            #
    # ------------------------------------------------------------------ #

    def test_bearer_secret_in_command_redacted(self):
        """A Bearer token in the command field must be redacted BEFORE
        storage — it must never appear in the SQLite DB."""
        secret = "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        oid = self.eph.add_observation(self.rag, "curl", "ok content",
                                        command=f"curl -H 'Authorization: {secret}'")
        obs = self.eph.get_observation(self.rag, oid)
        self.assertIsNotNone(obs)
        self.assertNotIn(secret, obs.get("command") or "",
                         "Bearer token must NOT be in the stored command")
        self.assertIn("REDACTED", obs.get("command") or "")

    def test_api_token_in_metadata_redacted(self):
        """An API token in metadata must be redacted BEFORE storage."""
        secret = "sk-abcdefghijklmnopqrstuvwxyz1234567890"
        oid = self.eph.add_observation(self.rag, "tool", "ok content",
                                        metadata={"api_key": secret})
        obs = self.eph.get_observation(self.rag, oid)
        self.assertIsNotNone(obs)
        meta = obs.get("metadata") or {}
        # The raw secret must NOT appear in the stored metadata.
        meta_str = json.dumps(meta) if not isinstance(meta, str) else meta
        self.assertNotIn(secret, meta_str,
                         "API token must NOT be in stored metadata")
        # Redaction marker must be present.
        self.assertTrue(
            any("redacted" in str(k).lower() or "redacted" in str(v).lower()
                for k, v in meta.items()) if isinstance(meta, dict)
            else "redacted" in str(meta).lower(),
            f"metadata must contain a redaction marker: {meta}")

    def test_raw_secret_not_in_sqlite(self):
        """The raw secret must not appear ANYWHERE in the .ephemeral.db file
        (binary scan). This is a defense-in-depth check beyond the API level."""
        secret = "ghp_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJ"
        self.eph.add_observation(self.rag, "tool", "ok content",
                                  command=f"git push {secret}",
                                  metadata={"token": secret})
        db_path = self.rag / ".ephemeral.db"
        raw = db_path.read_bytes()
        self.assertNotIn(secret.encode("utf-8"), raw,
                         "raw GitHub token must NOT appear in the SQLite file")

    def test_github_token_in_content_redacted(self):
        """A GitHub PAT (ghp_...) in content must be redacted."""
        secret = "ghp_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJ"
        oid = self.eph.add_observation(self.rag, "tool",
                                        f"using token {secret} for auth")
        obs = self.eph.get_observation(self.rag, oid)
        self.assertIsNotNone(obs)
        self.assertNotIn(secret, obs["content"])
        self.assertIn("REDACTED", obs["content"])

    def test_jwt_in_content_redacted(self):
        """A JWT in content must be redacted."""
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        oid = self.eph.add_observation(self.rag, "tool",
                                        f"auth token: {jwt}")
        obs = self.eph.get_observation(self.rag, oid)
        self.assertIsNotNone(obs)
        self.assertNotIn(jwt, obs["content"])
        self.assertIn("REDACTED", obs["content"])

    def test_openai_key_in_content_redacted(self):
        """An OpenAI-style key (sk-...) in content must be redacted."""
        secret = "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGHIJ"
        oid = self.eph.add_observation(self.rag, "tool",
                                        f"openai key: {secret}")
        obs = self.eph.get_observation(self.rag, oid)
        self.assertIsNotNone(obs)
        self.assertNotIn(secret, obs["content"])
        self.assertIn("REDACTED", obs["content"])


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

    # ------------------------------------------------------------------ #
    # BUG 1: multi-group regex must not produce tuple errors             #
    # ------------------------------------------------------------------ #

    def test_python_traceback_line_distilled_without_typeerror(self):
        """A Python traceback line 'src/foo.py:42: ValueError: bad input'
        must be distilled without a TypeError (multi-group regex returned
        tuples, but errors was treated as List[str])."""
        content = (
            "src/foo.py:42: ValueError: bad input\n"
            "1 failed in 0.1s\n"
        )
        d = self.distill.distill_output("pytest", content, command="pytest", exit_code=1)
        # errors must be a flat list of STRINGS (no tuples).
        self.assertIsInstance(d["errors"], list)
        for e in d["errors"]:
            self.assertIsInstance(e, str, f"error must be str, got {type(e)}: {e!r}")
        # The traceback line must appear (normalized) somewhere.
        self.assertTrue(any("ValueError" in e for e in d["errors"]),
                        f"ValueError line must be extracted; errors={d['errors']}")
        # Distillation must not raise; conclusion should be built.
        self.assertGreater(d["confidence"], 0.0)
        self.assertIn("ValueError", d["conclusion"])

    def test_errors_are_always_strings(self):
        """result['errors'] must always be List[str] regardless of pattern."""
        content = (
            "ERROR: something broke\n"
            "src/foo.py:42: ValueError: bad input\n"
            "FAILED test_x\n"
            "Traceback (most recent call last):\n"
            '  File "x.py", line 10, in test_x\n'
            "AssertionError: boom\n"
        )
        d = self.distill.distill_output("pytest", content, command="pytest", exit_code=1)
        self.assertIsInstance(d["errors"], list)
        for e in d["errors"]:
            self.assertIsInstance(e, str, f"errors must be str, got {type(e)}: {e!r}")
        # The conclusion must build without a TypeError from tuple-joining.
        self.assertGreater(d["confidence"], 0.0)
        self.assertIsInstance(d["conclusion"], str)
        self.assertIsInstance(d["evidence_excerpt"], str)

    # ------------------------------------------------------------------ #
    # BUG 2: suggested_remediation vs verified_fix semantics              #
    # ------------------------------------------------------------------ #

    def test_to_fix_is_suggested_remediation_not_verified_fix(self):
        """'To fix: increase timeout' must be labeled 'Suggested remediation',
        NOT 'Verified fix'. The distillation layer never auto-heuristics
        'verified' — it is a deterministic extraction, not a verification."""
        content = (
            "FAILED test_timeout\n"
            "AssertionError: timed out\n"
            "To fix: increase timeout\n"
        )
        d = self.distill.distill_output("pytest", content, command="pytest", exit_code=1)
        self.assertTrue(d["should_promote"], f"expected promotion: {d}")
        result = self.distill.distill_to_memory_body(d)
        self.assertIsNotNone(result, f"expected a body: {d}")
        title, body = result
        self.assertIn("Suggested remediation", body)
        self.assertIn("increase timeout", body)
        self.assertNotIn("Verified fix", body,
                         "unverified distillation must NOT use 'Verified fix'")

    def test_fix_colon_is_suggested_remediation(self):
        """'fix: ...' is also a suggestion, not a verification."""
        content = (
            "ERROR: connection refused\n"
            "fix: check the firewall rules\n"
        )
        d = self.distill.distill_output("ssh", content, command="ssh", exit_code=1)
        if d["should_promote"]:
            result = self.distill.distill_to_memory_body(d)
            self.assertIsNotNone(result)
            _, body = result
            self.assertIn("Suggested remediation", body)
            self.assertNotIn("Verified fix", body)

    def test_resolved_is_suggested_remediation(self):
        """'resolved: ...' is also a suggestion, not a verification."""
        content = (
            "FAILED test_x\n"
            "resolved: restart the service\n"
        )
        d = self.distill.distill_output("pytest", content, command="pytest", exit_code=1)
        if d["should_promote"]:
            result = self.distill.distill_to_memory_body(d)
            self.assertIsNotNone(result)
            _, body = result
            self.assertIn("Suggested remediation", body)
            self.assertNotIn("Verified fix", body)

    def test_explicit_verified_flag_labels_verified_fix(self):
        """promote --verified is an explicit user assertion: the body must
        then label 'Verified fix' (not 'Suggested remediation')."""
        content = (
            "FAILED test_x\n"
            "AssertionError: bad value\n"
            "To fix: increase timeout\n"
        )
        d = self.distill.distill_output("pytest", content, command="pytest", exit_code=1)
        self.assertTrue(d["should_promote"])
        # Default (no --verified): suggested
        result_default = self.distill.distill_to_memory_body(d, verified=False)
        self.assertIsNotNone(result_default)
        _, body_default = result_default
        self.assertIn("Suggested remediation", body_default)
        self.assertNotIn("Verified fix", body_default)
        # Explicit --verified: verified
        result_verified = self.distill.distill_to_memory_body(d, verified=True)
        self.assertIsNotNone(result_verified)
        _, body_verified = result_verified
        self.assertIn("Verified fix", body_verified)
        self.assertIn("increase timeout", body_verified)

    def test_no_remediation_no_label(self):
        """If no remediation is extracted, neither label appears in the body."""
        content = (
            "FAILED test_x\n"
            "AssertionError: bad value\n"
        )
        d = self.distill.distill_output("pytest", content, command="pytest", exit_code=1)
        self.assertTrue(d["should_promote"])
        result = self.distill.distill_to_memory_body(d)
        self.assertIsNotNone(result)
        _, body = result
        self.assertNotIn("Suggested remediation", body)
        self.assertNotIn("Verified fix", body)


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
        # Create a stale lock (old timestamp + dead PID)
        lock_path.write_text(f"99999\n{time.time() - 300}\nabc-token\n", encoding="ascii")
        with self.atomic.ProjectWriteLock(lock_path, timeout=2, stale_seconds=60):
            self.assertTrue(lock_path.exists())
        self.assertFalse(lock_path.exists())

    def test_lockfile_contains_ownership_token(self):
        """Each lock file must contain PID + timestamp + random ownership token."""
        lock_path = self.tmp / ".write.lock"
        lock = self.atomic.ProjectWriteLock(lock_path, timeout=2)
        lock.acquire()
        content = lock_path.read_text(encoding="ascii")
        lines = content.strip().split("\n")
        self.assertGreaterEqual(len(lines), 3, "lock file must have 3 lines (pid/ts/token)")
        self.assertTrue(lines[0].strip().isdigit())
        float(lines[1].strip())
        self.assertTrue(lines[2].strip(), "token line must be non-empty")
        lock.release()

    def test_release_does_not_delete_foreign_lock(self):
        """A stale owner releasing must NOT delete a lock owned by a new token."""
        lock_path = self.tmp / ".write.lock"
        # Simulate: old owner acquires, then a NEW owner reclaims it.
        old_lock = self.atomic.ProjectWriteLock(lock_path, timeout=2, stale_seconds=0.1)
        old_lock.acquire()
        old_token = old_lock._token
        self.assertTrue(old_token)
        # New owner (simulated by rewriting the lock file with a different token)
        new_token = "new-owner-token-12345"
        lock_path.write_text(f"{os.getpid()}\n{time.time()}\n{new_token}\n", encoding="ascii")
        # Old owner releases — must NOT delete the new owner's lock file
        old_lock.release()
        self.assertTrue(lock_path.exists(),
                        "stale owner must not delete the new owner's lock file")
        self.assertEqual(
            lock_path.read_text(encoding="ascii").strip().split("\n")[2],
            new_token)


class TestLockMultiprocess(unittest.TestCase):
    """Multiprocess lock tests (not just threads).

    Spawns child processes to verify:
    - a live holder's lock is NOT stolen on age alone;
    - after the holder exits, the lock IS reclaimable;
    - a stale owner's release does not delete a new owner's lock;
    - a dead stale PID is reclaimed.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lock-mp-"))
        self.lock_path = self.tmp / ".write.lock"
        self.atomic = _load_module("atomic_mp", ATOMIC_PATH)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _dead_pid() -> int:
        """Return a PID that is guaranteed to be dead (spawn + wait)."""
        import subprocess
        p = subprocess.Popen([sys.executable, "-c", "pass"],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        p.wait(timeout=10)
        return p.pid

    def _spawn_holder(self, hold_seconds: float):
        """Spawn a child process that acquires the lock, holds it, then exits.
        Returns the Popen object."""
        code = (
            "import sys, time, importlib.util\n"
            "spec = importlib.util.spec_from_file_location('a', %r)\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "lock = mod.ProjectWriteLock(%r, timeout=5, stale_seconds=1)\n"
            "lock.acquire()\n"
            "print('HELD', flush=True)\n"
            "time.sleep(%r)\n"
            "lock.release()\n"
            "print('RELEASED', flush=True)\n"
            "sys.exit(0)\n"
        ) % (str(ATOMIC_PATH), str(self.lock_path), hold_seconds)
        import subprocess
        p = subprocess.Popen([sys.executable, "-c", code],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True)
        # Wait for the child to print HELD (lock acquired)
        line = p.stdout.readline() if p.stdout else ""
        self.assertIn("HELD", line)
        return p

    def _wait_and_close(self, proc) -> None:
        try:
            proc.stdout.read()
        except Exception:
            pass
        proc.wait(timeout=15)
        try:
            proc.stderr.read()
        except Exception:
            pass

    def test_live_holder_not_stolen_on_age(self):
        """Process A holds the lock >2s (stale_seconds=1). Process B
        must NOT be able to steal it while A is alive."""
        p = self._spawn_holder(hold_seconds=3)
        try:
            # Try to acquire from THIS process — should time out (A is alive)
            lock_b = self.atomic.ProjectWriteLock(
                self.lock_path, timeout=2, stale_seconds=1, poll_interval=0.05)
            try:
                lock_b.acquire()
                self.fail("B should NOT acquire while A is alive")
            except TimeoutError:
                pass  # expected
        finally:
            self._wait_and_close(p)
    def test_dead_holder_reclaimable(self):
        """After process A exits (releases), B can acquire."""
        p = self._spawn_holder(hold_seconds=1)
        self._wait_and_close(p)
        # A has released; the lock file should be gone (or reclaimable)
        lock_b = self.atomic.ProjectWriteLock(
            self.lock_path, timeout=3, stale_seconds=1, poll_interval=0.05)
        lock_b.acquire()
        self.assertTrue(self.lock_path.exists())
        lock_b.release()

    def test_stale_owner_release_does_not_stomp_new_owner(self):
        """Process A acquires, dies without releasing.
        B reclaims. A's late release must NOT delete B's lock."""
        code = (
            "import sys, time, importlib.util\n"
            "spec = importlib.util.spec_from_file_location('a', %r)\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "lock = mod.ProjectWriteLock(%r, timeout=5, stale_seconds=1)\n"
            "lock.acquire()\n"
            "print('HELD', flush=True)\n"
            "time.sleep(30)\n"
        ) % (str(ATOMIC_PATH), str(self.lock_path))
        import subprocess
        p = subprocess.Popen([sys.executable, "-c", code],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True)
        line = p.stdout.readline()
        self.assertIn("HELD", line)
        # Kill A (simulates crash — no release)
        p.kill()
        p.wait()
        # B reclaims (A's PID is dead)
        lock_b = self.atomic.ProjectWriteLock(
            self.lock_path, timeout=3, stale_seconds=1, poll_interval=0.05)
        lock_b.acquire()
        self.assertTrue(self.lock_path.exists())
        # Simulate A's late release (A's token no longer matches file)
        a_lock = self.atomic.ProjectWriteLock(
            self.lock_path, timeout=2, stale_seconds=1)
        a_lock._token = "stale-a-token-that-does-not-match"
        a_lock.release()  # must NOT delete B's lock
        self.assertTrue(self.lock_path.exists(),
                        "stale owner release must not delete new owner's lock")
        lock_b.release()

    def test_dead_stale_pid_reclaimed(self):
        """A lock file with a dead PID and old timestamp is reclaimed."""
        dead_pid = self._dead_pid()
        self.lock_path.write_text(
            f"{dead_pid}\n{time.time() - 999}\nold-token\n", encoding="ascii")
        lock = self.atomic.ProjectWriteLock(
            self.lock_path, timeout=3, stale_seconds=1, poll_interval=0.05)
        lock.acquire()
        self.assertTrue(self.lock_path.exists())
        self.assertNotEqual(lock._token, "old-token")
        lock.release()

    def test_dead_pid_always_reclaimable_posix(self):
        """Even with a FRESH timestamp, a dead PID is reclaimable."""
        dead_pid = self._dead_pid()
        # Fresh timestamp (age=0) but dead PID → must still be reclaimable
        self.lock_path.write_text(
            f"{dead_pid}\n{time.time()}\nfresh-but-dead\n", encoding="ascii")
        lock = self.atomic.ProjectWriteLock(
            self.lock_path, timeout=3, stale_seconds=1, poll_interval=0.05)
        lock.acquire()
        self.assertTrue(self.lock_path.exists())
        lock.release()


if __name__ == "__main__":
    unittest.main(verbosity=2)