#!/usr/bin/env python3
"""End-to-end ephemeral lifecycle test (P7 + P20).

Pipeline under test (subprocess, exactly as an agent would use it):

  raw tool output
    -> `observe`            (ephemeral observation, TTL-bounded, redacted)
    -> `promote`            (distillation -> admission -> durable memory)
    -> raw observation DELETED
    -> `gc --apply`         (retention; archived metadata stamped)
    -> provenance            (source_observation + content hash in durable FM)

Zero external dependencies. Python 3.8+ stdlib only.
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
MLM = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "mlm.py"

FAILED_OUTPUT = (
    "42 passed, 1 failed in 3.2s\n"
    "Traceback (most recent call last):\n"
    '  File "src/auth.py", line 42, in login\n'
    "    assert token is not None\n"
    "AssertionError: token is None\n"
)

BENIGN_OUTPUT = "All 100 tests passed in 2.3s\nOK\n"


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run([sys.executable, str(MLM), *args], cwd=str(cwd),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=120, env=env)


def _last_json(stdout: str) -> Any:
    """Parse the LAST JSON value in stdout (some commands emit several).

    Search returns a JSON ARRAY; other commands return JSON OBJECTS. This
    helper returns whichever JSON value appears last on stdout (dict OR list).
    """
    last: Any = {}
    decoder = json.JSONDecoder()
    s = stdout.replace("\ufeff", "").strip()
    i = 0
    while i < len(s):
        while i < len(s) and s[i] in " \t\r\n":
            i += 1
        if i >= len(s):
            break
        try:
            obj, end = decoder.raw_decode(s, i)
        except json.JSONDecodeError:
            i += 1
            continue
        last = obj
        i = end
    return last


def _new_project() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="e2e-lifecycle-"))
    subprocess.run(["git", "init", "-q", str(tmp)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return tmp


class TestEphemeralLifecycleE2E(unittest.TestCase):
    """Full pipeline: observe -> promote -> raw deletion -> gc."""

    def setUp(self):
        self.proj = _new_project()
        r = _run(self.proj, "init")
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))

    def tearDown(self):
        shutil.rmtree(self.proj, ignore_errors=True)

    def _observe(self, content: str, source: str = "pytest",
                 command: str = "pytest", exit_code: int = 1) -> int:
        f = self.proj / "out.txt"
        f.write_text(content, encoding="utf-8")
        r = _run(self.proj, "observe", "--file", "out.txt",
                 "--source", source, "--command", command,
                 "--exit-code", str(exit_code), "--json")
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        out = _last_json(r.stdout.decode("utf-8"))
        self.assertEqual(out["durable"], False)
        return int(out["observation_id"])

    def test_full_pipeline_failed_output(self):
        """A real failure is promoted to a durable memory with provenance,
        and the raw ephemeral observation is deleted."""
        oid = self._observe(FAILED_OUTPUT)
        r = _run(self.proj, "promote", "--observation-id", str(oid), "--json")
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        out = _last_json(r.stdout.decode("utf-8"))
        self.assertTrue(out["promoted"], out)
        prov = out["provenance"]
        self.assertEqual(prov["source_observation"], oid)
        self.assertTrue(prov["content_hash"])

        # durable memory exists with provenance frontmatter
        failures = list((self.proj / "INTERNAL_RAG" / "failures").glob("*.md"))
        self.assertEqual(len(failures), 1)
        fm_text = failures[0].read_text(encoding="utf-8")
        self.assertIn(f"source_observation: {oid}", fm_text)
        self.assertIn(f"obs_content_hash: {prov['content_hash']}", fm_text)
        self.assertIn("AssertionError", fm_text)

        # raw observation is DELETED (lifecycle end)
        stats = self._gc_dry()
        self.assertEqual(stats["ephemeral"]["count"], 0,
                         "raw observation must be deleted after promotion")

        # searchable
        r = _run(self.proj, "search", "--query", "AssertionError token", "--json")
        self.assertEqual(r.returncode, 0)
        sres = _last_json(r.stdout.decode("utf-8"))
        if isinstance(sres, dict):
            results = sres.get("results", [])
        else:
            results = sres  # search returns a JSON array
        self.assertGreater(len(results), 0,
                          f"promoted failure must be searchable: {sres}")

    def test_benign_output_not_promoted(self):
        """A passing test run has no root cause -> stays ephemeral."""
        oid = self._observe(BENIGN_OUTPUT, exit_code=0)
        r = _run(self.proj, "promote", "--observation-id", str(oid), "--json")
        # admission failed -> NOT promoted; observation still ephemeral
        out = _last_json(r.stdout.decode("utf-8"))
        self.assertFalse(out.get("promoted", True),
                         f"benign output must not be promoted: {out}")
        self.assertEqual(len(list((self.proj / "INTERNAL_RAG" / "failures").glob("*.md"))), 0)

    def test_expired_observation_cannot_promote(self):
        """An expired (TTL'd out) observation must be rejected by promote."""
        # create with TTL=1 via observe (default TTL is long; use gc to force expiry)
        oid = self._observe(FAILED_OUTPUT)
        # Force expiry: manipulate the DB TTL directly
        import sqlite3
        for db_name in (".index.sqlite3", ".ephemeral.db"):
            db = self.proj / "INTERNAL_RAG" / db_name
            if db.exists():
                conn = sqlite3.connect(str(db))
                conn.execute("UPDATE ephemeral_observations SET expires_at = 0")
                conn.commit()
                conn.close()
                break
        r = _run(self.proj, "promote", "--observation-id", str(oid), "--json")
        self.assertNotEqual(r.returncode, 0)

    def test_gc_apply_archives_stale_memory(self):
        """gc --apply archives a stale low-value memory, stamping
        archived_at + status: archived before moving (P11).

        A 400-day-old *session* with confidence: low scores < 0.3 (type_score
        0.1, recency 0, confidence low 0.3, evidence 0.7), qualifying for
        archival once age > gc_candidate_days (180).
        """
        import datetime as _dt
        old = (_dt.date.today() - _dt.timedelta(days=400)).isoformat()
        mem_dir = self.proj / "INTERNAL_RAG" / "sessions"
        mem_dir.mkdir(parents=True, exist_ok=True)
        mem = mem_dir / "stale-e2e.md"
        mem.write_text(
            f"---\nid: mem-e2e-stale\ntype: session\nstatus: active\n"
            f"created: {old}\nconfidence: low\nscope: []\ntags: []\nsources: []\nlinks: []\n---\n\n"
            "# stale\n\n## Knowledge\n\nold session\n\n## Consequence\n\nNone.\n",
            encoding="utf-8")
        r = _run(self.proj, "gc", "--apply", "--json")
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        applied = _last_json(r.stdout.decode("utf-8"))
        self.assertGreaterEqual(applied["executed"]["archived"], 1,
                                f"expected archive, got: {applied['executed']}")
        archived = self.proj / "INTERNAL_RAG" / "archive" / "stale-e2e.md"
        self.assertTrue(archived.exists(), "stale memory must be moved to archive")
        text = archived.read_text(encoding="utf-8")
        self.assertIn("archived_at:", text, "archived_at stamped before move")
        import re
        self.assertTrue(re.search(r"^status: archived\s*$", text, re.MULTILINE))

    def test_gc_dry_run_does_not_move(self):
        import datetime as _dt
        old = (_dt.date.today() - _dt.timedelta(days=400)).isoformat()
        mem_dir = self.proj / "INTERNAL_RAG" / "sessions"
        mem_dir.mkdir(parents=True, exist_ok=True)
        mem = mem_dir / "stale-dry.md"
        mem.write_text(
            f"---\nid: mem-e2e-dry\ntype: session\nstatus: active\n"
            f"created: {old}\nconfidence: low\nscope: []\ntags: []\nsources: []\nlinks: []\n---\n\n"
            "# dry\n\n## Knowledge\n\nx\n\n## Consequence\n\nNone.\n",
            encoding="utf-8")
        r = _run(self.proj, "gc", "--json")
        self.assertEqual(r.returncode, 0)
        dry = _last_json(r.stdout.decode("utf-8"))
        self.assertEqual(dry["applied"], False)
        self.assertTrue(mem.exists(), "dry-run must NOT move files")
        self.assertFalse((self.proj / "INTERNAL_RAG" / "archive" / "stale-dry.md").exists())

    def _gc_dry(self) -> Any:
        r = _run(self.proj, "gc", "--json")
        self.assertEqual(r.returncode, 0)
        return _last_json(r.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
