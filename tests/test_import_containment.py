#!/usr/bin/env python3
"""Regression tests for import path containment (P-import-security).

Ensures `import_cmd` NEVER writes outside INTERNAL_RAG, regardless of the
path strings in the import bundle.

Covered escape vectors:
  - valid INTERNAL_RAG/knowledge/x.md imports successfully;
  - ../ escape rejected;
  - ../../ escape rejected;
  - absolute escape rejected (POSIX and Windows-style);
  - symlink-to-outside escape rejected (where symlinks are supported);
  - --overwrite still works only inside RAG;
  - no file outside RAG is ever created.
"""
from __future__ import annotations
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
IRAG_PATH = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag.py"

_spec = __import__("importlib.util").util.spec_from_file_location("irag_imp", str(IRAG_PATH))
irag = __import__("importlib.util").util.module_from_spec(_spec)
_spec.loader.exec_module(irag)


def _can_symlink() -> bool:
    """True if the platform + filesystem supports symlinks."""
    if sys.platform == "win32":
        # On Windows, symlinks require admin or developer mode; try for real.
        try:
            with tempfile.TemporaryDirectory() as td:
                target = Path(td) / "real.txt"
                target.write_text("x", encoding="utf-8")
                link = Path(td) / "link"
                os.symlink(target, link)
                return True
        except OSError:
            return False
    return True


class Env:
    """Redirect irag.ROOT/RAG to a fresh sandbox INTERNAL_RAG tree."""

    def __init__(self, sandbox: Path):
        self.sandbox = sandbox
        self.rag = sandbox / "INTERNAL_RAG"
        for d in ["decisions", "knowledge", "gotchas", "failures",
                  "hypotheses", "sessions", "archive"]:
            (self.rag / d).mkdir(parents=True, exist_ok=True)

    def __enter__(self):
        self._old = (irag.ROOT, irag.RAG, irag.CONFIG_PATH,
                     irag._open_sqlite_index, irag.rebuild_index)
        irag.ROOT = self.sandbox
        irag.RAG = self.rag
        irag.CONFIG_PATH = self.sandbox / ".irag.yml"
        irag._open_sqlite_index = lambda: None
        irag.rebuild_index = lambda: None
        return self

    def __exit__(self, *a):
        (irag.ROOT, irag.RAG, irag.CONFIG_PATH,
         irag._open_sqlite_index, irag.rebuild_index) = self._old


class ImportArgs:
    def __init__(self, file: str, overwrite: bool = False):
        self.file = file
        self.overwrite = overwrite


def _bundle(tmp: Path, memories: list) -> Path:
    payload = {"memories": memories}
    f = tmp / "bundle.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    return f


def _content(name: str = "test") -> str:
    return (
        f"---\nid: mem-imp-{name}\ntype: knowledge\nstatus: active\n"
        f"created: 2024-01-01\nscope: []\ntags: []\n---\n\n"
        f"# {name}\n\n## Knowledge\n\nbody\n\n## Consequence\n\nNone.\n"
    )


class TestImportPathContainment(unittest.TestCase):
    """Import must never write outside INTERNAL_RAG."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="imp-sec-"))
        self.outside = self.tmp / "outside"
        self.outside.mkdir(exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _import(self, bundle: Path, overwrite: bool = False) -> int:
        with Env(self.tmp / "proj"):
            with redirect_stdout(io.StringIO()):
                return irag.import_cmd(ImportArgs(str(bundle), overwrite=overwrite))

    def _outside_files(self) -> list:
        return list(self.outside.glob("**/*"))

    # ------------------------------------------------------------------ #
    # valid import                                                       #
    # ------------------------------------------------------------------ #

    def test_valid_internal_rag_knowledge_imports(self):
        """A well-formed INTERNAL_RAG/knowledge/x.md imports successfully."""
        bundle = _bundle(self.tmp, [{
            "path": "INTERNAL_RAG/knowledge/x.md",
            "content": _content("x"),
        }])
        with Env(self.tmp / "proj") as env:
            with redirect_stdout(io.StringIO()):
                rc = irag.import_cmd(ImportArgs(str(bundle)))
            self.assertEqual(rc, 0)
            self.assertTrue((env.rag / "knowledge" / "x.md").exists())
        self.assertEqual(self._outside_files(), [])

    # ------------------------------------------------------------------ #
    # escape attempts rejected                                           #
    # ------------------------------------------------------------------ #

    def test_dotdot_escape_rejected(self):
        """INTERNAL_RAG/../outside.md must NOT write outside RAG."""
        target = self.outside / "escape1.md"
        bundle = _bundle(self.tmp, [{
            "path": "INTERNAL_RAG/../outside/escape1.md",
            "content": _content("escape1"),
        }])
        rc = self._import(bundle)
        self.assertEqual(rc, 0)
        self.assertFalse(target.exists(),
                         "INTERNAL_RAG/../outside/escape1.md must not write outside RAG")
        self.assertEqual(self._outside_files(), [])

    def test_double_dotdot_escape_rejected(self):
        """INTERNAL_RAG/../../outside.md must NOT write outside RAG."""
        target = self.outside / "escape2.md"
        bundle = _bundle(self.tmp, [{
            "path": "INTERNAL_RAG/../../outside/escape2.md",
            "content": _content("escape2"),
        }])
        rc = self._import(bundle)
        self.assertEqual(rc, 0)
        self.assertFalse(target.exists())
        self.assertEqual(self._outside_files(), [])

    def test_absolute_path_rejected(self):
        """An absolute path must NOT be honored as a destination."""
        # Build an absolute path inside `outside` (so it definitely does not
        # live under RAG).
        abs_target = self.outside / "abs.md"
        abs_path = str(abs_target)
        bundle = _bundle(self.tmp, [{
            "path": abs_path,
            "content": _content("abs"),
        }])
        rc = self._import(bundle)
        self.assertEqual(rc, 0)
        self.assertFalse(abs_target.exists(),
                         "absolute path must not be written outside RAG")
        self.assertEqual(self._outside_files(), [])

    def test_windows_style_drive_path_rejected(self):
        """A Windows-style drive path (C:/...) must be rejected on all
        platforms (defensive: the helper rejects by prefix even on POSIX)."""
        bundle = _bundle(self.tmp, [{
            "path": "C:/WINDOWS/Temp/evil.md",
            "content": _content("cdrive"),
        }])
        rc = self._import(bundle)
        self.assertEqual(rc, 0)
        self.assertEqual(self._outside_files(), [])

    def test_unc_path_rejected(self):
        """A UNC //server/share path must be rejected."""
        bundle = _bundle(self.tmp, [{
            "path": "//evil/share/escape.md",
            "content": _content("unc"),
        }])
        rc = self._import(bundle)
        self.assertEqual(rc, 0)
        self.assertEqual(self._outside_files(), [])

    # ------------------------------------------------------------------ #
    # symlink-to-outside                                                  #
    # ------------------------------------------------------------------ #

    @unittest.skipUnless(_can_symlink(), "symlinks not supported on this platform/fs")
    def test_symlink_to_outside_rejected(self):
        """A symlinked directory inside RAG that points OUTSIDE RAG must not
        let an import entry escape through it."""
        with Env(self.tmp / "proj") as env:
            # Create a symlink: INTERNAL_RAG/knowledge_evil -> outside/
            link_dir = env.rag / "knowledge_evil"
            os.symlink(self.outside, link_dir)
            # Import entry targets the symlinked dir.
            bundle = _bundle(self.tmp, [{
                "path": "INTERNAL_RAG/knowledge_evil/escape3.md",
                "content": _content("escape3"),
            }])
            with redirect_stdout(io.StringIO()):
                rc = irag.import_cmd(ImportArgs(str(bundle)))
            self.assertEqual(rc, 0)
            target = self.outside / "escape3.md"
            self.assertFalse(target.exists(),
                             "symlink traversal must not write outside RAG")
        self.assertEqual(self._outside_files(), [])

    @unittest.skipUnless(_can_symlink(), "symlinks not supported on this platform/fs")
    def test_symlinked_subdir_inside_rag_still_imports(self):
        """A symlink pointing INSIDE RAG should still allow import (regression
        guard: containment must not over-reject valid intra-RAG symlinks)."""
        with Env(self.tmp / "proj") as env:
            real_dir = env.rag / "knowledge"
            link_dir = env.rag / "knowledge_alias"
            os.symlink(real_dir, link_dir)
            bundle = _bundle(self.tmp, [{
                "path": "INTERNAL_RAG/knowledge_alias/ok.md",
                "content": _content("ok"),
            }])
            with redirect_stdout(io.StringIO()):
                rc = irag.import_cmd(ImportArgs(str(bundle)))
            self.assertEqual(rc, 0)
            # File must land inside RAG (via the symlink), never outside.
            self.assertTrue((env.rag / "knowledge" / "ok.md").exists()
                            or (env.rag / "knowledge_alias" / "ok.md").exists())
        self.assertEqual(self._outside_files(), [])

    # ------------------------------------------------------------------ #
    # --overwrite still works inside RAG                                 #
    # ------------------------------------------------------------------ #

    def test_overwrite_inside_rag(self):
        """--overwrite replaces an existing file INSIDE RAG; nothing outside."""
        bundle = _bundle(self.tmp, [{
            "path": "INTERNAL_RAG/knowledge/ow.md",
            "content": _content("ow-v1"),
        }])
        with Env(self.tmp / "proj") as env:
            with redirect_stdout(io.StringIO()):
                irag.import_cmd(ImportArgs(str(bundle), overwrite=False))
            p = env.rag / "knowledge" / "ow.md"
            self.assertTrue(p.exists())
            self.assertIn("ow-v1", p.read_text(encoding="utf-8"))
            # overwrite with v2
            bundle2 = _bundle(self.tmp, [{
                "path": "INTERNAL_RAG/knowledge/ow.md",
                "content": _content("ow-v2"),
            }])
            with redirect_stdout(io.StringIO()):
                irag.import_cmd(ImportArgs(str(bundle2), overwrite=True))
            self.assertIn("ow-v2", p.read_text(encoding="utf-8"))
        self.assertEqual(self._outside_files(), [])

    def test_overwrite_does_not_create_outside_file(self):
        """An overwrite entry that escapes is rejected; no outside file is
        created (even if a same-named file already exists outside)."""
        outside_file = self.outside / "ow-escape.md"
        outside_file.write_text("pre-existing", encoding="utf-8")
        bundle = _bundle(self.tmp, [{
            "path": "INTERNAL_RAG/../outside/ow-escape.md",
            "content": _content("overwrite-escape"),
        }])
        rc = self._import(bundle, overwrite=True)
        self.assertEqual(rc, 0)
        self.assertEqual(outside_file.read_text(encoding="utf-8"), "pre-existing",
                         "overwrite-escape must not modify the outside file")
        self.assertEqual(self._outside_files(), [outside_file])

    # ------------------------------------------------------------------ #
    # mixed bundle: valid + invalid entries                              #
    # ------------------------------------------------------------------ #

    def test_mixed_bundle_imports_valid_rejects_invalid(self):
        """A bundle with one valid and one escaping entry must import the
        valid one and reject the invalid one — no file outside RAG."""
        bundle = _bundle(self.tmp, [
            {"path": "INTERNAL_RAG/knowledge/good.md",
             "content": _content("good")},
            {"path": "INTERNAL_RAG/../outside/bad.md",
             "content": _content("bad")},
        ])
        with Env(self.tmp / "proj") as env:
            with redirect_stdout(io.StringIO()):
                rc = irag.import_cmd(ImportArgs(str(bundle)))
            self.assertEqual(rc, 0)
            self.assertTrue((env.rag / "knowledge" / "good.md").exists())
        self.assertFalse((self.outside / "bad.md").exists())
        self.assertEqual(self._outside_files(), [])


class TestSafeImportDestinationUnit(unittest.TestCase):
    """Direct unit tests for the _safe_import_destination helper."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="imp-helper-"))
        self.rag = self.tmp / "INTERNAL_RAG"
        (self.rag / "knowledge").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid_relative(self):
        d = irag._safe_import_destination(self.rag, "INTERNAL_RAG/knowledge/x.md")
        self.assertIsNotNone(d)
        self.assertEqual(d.name, "x.md")

    def test_strips_internal_rag_prefix(self):
        d = irag._safe_import_destination(self.rag, "knowledge/y.md")
        self.assertIsNotNone(d)
        self.assertEqual(d.name, "y.md")

    def test_dotdot_rejected(self):
        self.assertIsNone(
            irag._safe_import_destination(self.rag, "INTERNAL_RAG/../outside.md"))

    def test_absolute_rejected(self):
        self.assertIsNone(
            irag._safe_import_destination(self.rag, "/etc/passwd"))

    def test_windows_drive_rejected(self):
        self.assertIsNone(
            irag._safe_import_destination(self.rag, "C:/Windows/Temp/evil.md"))

    def test_unc_rejected(self):
        self.assertIsNone(
            irag._safe_import_destination(self.rag, "//server/share/x.md"))

    def test_empty_rejected(self):
        self.assertIsNone(irag._safe_import_destination(self.rag, ""))
        self.assertIsNone(irag._safe_import_destination(self.rag, None))

    def test_dot_only_rejected(self):
        self.assertIsNone(
            irag._safe_import_destination(self.rag, "INTERNAL_RAG/."))

    def test_nested_subdir_inside_rag_ok(self):
        d = irag._safe_import_destination(self.rag, "INTERNAL_RAG/knowledge/sub/deep.md")
        self.assertIsNotNone(d)
        self.assertEqual(d.name, "deep.md")


if __name__ == "__main__":
    unittest.main(verbosity=2)