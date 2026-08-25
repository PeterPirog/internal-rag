#!/usr/bin/env python3
"""A1 regression: fingerprint cache must never hide uncommitted tracked changes.

Correctness model (irag.py project_fingerprint):
- the tracked working-tree/index diff is ALWAYS hashed fresh, even when
  use_cache=True — a cached fingerprint must not mask a modified tracked file;
- the untracked-file digest MAY be cached, keyed by (HEAD, per-file rel+size+mtime).
"""
from __future__ import annotations
import importlib.util
import json
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
IRAG_PATH = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag.py"

_spec = importlib.util.spec_from_file_location("irag_mod", str(IRAG_PATH))
irag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(irag)


def _git(cwd: Path, *args: str) -> str:
    p = subprocess.run(
        ["git", "-C", str(cwd)] + list(args),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.stdout.strip()


class FingerprintCache(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="irag-fp-cache-"))
        _git(self.tmp, "init")
        _git(self.tmp, "config", "user.email", "t@e.com")
        _git(self.tmp, "config", "user.name", "t")
        (self.tmp / "app.py").write_text("print('v1')\n", encoding="utf-8")
        _git(self.tmp, "add", ".")
        _git(self.tmp, "commit", "-m", "init")
        self._old = (irag.ROOT, irag.RAG, irag.FP_CACHE, irag.CHECKPOINT,
                     irag.CONFIG_PATH, irag.WORKING)
        irag.ROOT = self.tmp
        irag.RAG = self.tmp / "INTERNAL_RAG"
        irag.RAG.mkdir(parents=True, exist_ok=True)
        irag.FP_CACHE = irag.RAG / ".fpcache.json"
        irag.CHECKPOINT = irag.RAG / ".checkpoint.json"
        irag.CONFIG_PATH = self.tmp / ".irag.yml"
        irag.WORKING = irag.RAG / "WORKING_STATE.md"

    def tearDown(self):
        irag.ROOT, irag.RAG, irag.FP_CACHE, irag.CHECKPOINT, irag.CONFIG_PATH, irag.WORKING = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_untracked_digest_is_cached_when_unchanged(self):
        (self.tmp / "notes.md").write_text("untracked body one\n", encoding="utf-8")
        first = irag.project_fingerprint(use_cache=True)
        self.assertTrue(irag.FP_CACHE.exists(), "cache file should have been written")
        second = irag.project_fingerprint(use_cache=True)
        self.assertEqual(first, second)

    def test_cache_does_not_hide_tracked_change(self):
        """A1: modifying a TRACKED file must change the fingerprint even with use_cache=True."""
        (self.tmp / "notes.md").write_text("untracked body one\n", encoding="utf-8")
        fp_before = irag.project_fingerprint(use_cache=True)
        self.assertTrue(irag.FP_CACHE.exists())
        (self.tmp / "app.py").write_text("print('v2-modified')\n", encoding="utf-8")
        fp_after = irag.project_fingerprint(use_cache=True)
        self.assertNotEqual(fp_before, fp_after,
                            "cached fingerprint must never hide an uncommitted tracked change")

    def test_cache_invalidation_on_untracked_content_change(self):
        """Untracked content change with a NEW size must change the digest."""
        (self.tmp / "notes.md").write_text("abc\n", encoding="utf-8")
        fp1 = irag.project_fingerprint(use_cache=True)
        time.sleep(0.02)
        (self.tmp / "notes.md").write_text("abcd longer now\n", encoding="utf-8")
        fp2 = irag.project_fingerprint(use_cache=True)
        self.assertNotEqual(fp1, fp2)

    def test_guard_detects_change_after_cache(self):
        """End-to-end: guard must report STALE after a tracked edit, cache present."""
        (self.tmp / "notes.md").write_text("untracked\n", encoding="utf-8")
        cp_fp = irag.project_fingerprint(use_cache=True)
        irag.CHECKPOINT.write_text(json.dumps({"fingerprint": cp_fp, "at": irag.now()}), encoding="utf-8")
        self.assertEqual(irag.guard(), 0)
        (self.tmp / "app.py").write_text("print('v3')\n", encoding="utf-8")
        self.assertEqual(irag.guard(), 2, "guard must be STALE after tracked edit")

    def test_staged_change_also_detected(self):
        """Tracked change staged in the index (diff --cached) must also be detected."""
        (self.tmp / "notes.md").write_text("untracked\n", encoding="utf-8")
        fp1 = irag.project_fingerprint(use_cache=True)
        (self.tmp / "app.py").write_text("print('staged')\n", encoding="utf-8")
        _git(self.tmp, "add", "app.py")
        fp2 = irag.project_fingerprint(use_cache=True)
        self.assertNotEqual(fp1, fp2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
