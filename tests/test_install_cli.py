#!/usr/bin/env python3
"""Test that zero-shot setup commands match install.py argparse interface.

Regression test for the drift documented in the Warp installation feedback
(prompt said --target/--shared-tools but install.py only accepts
[repo] [--share-tools]).
"""
from __future__ import annotations
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
INSTALL_PY = PROJECT_ROOT / "install.py"
PROMPTS_MD = PROJECT_ROOT / "docs" / "ZERO-SHOT-SETUP-PROMPTS.md"


def _install_help() -> str:
    p = subprocess.run([sys.executable, str(INSTALL_PY), "--help"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, encoding="utf-8", timeout=30)
    return p.stdout


class TestZeroShotPromptsMatchInstaller(unittest.TestCase):
    def test_prompts_doc_exists(self):
        self.assertTrue(PROMPTS_MD.exists(), "ZERO-SHOT-SETUP-PROMPTS.md missing")

    def test_no_drifted_flags(self):
        """The prompts must not use flags that install.py does not accept."""
        text = PROMPTS_MD.read_text(encoding="utf-8")
        # These were the drifted flags from the first version.
        self.assertNotIn("--target ", text, "drifted --target flag still in prompts")
        self.assertNotIn("--shared-tools", text, "drifted --shared-tools flag still in prompts")

    def test_prompts_use_correct_flags(self):
        text = PROMPTS_MD.read_text(encoding="utf-8")
        self.assertIn("--client warp", text)
        self.assertIn("--client opencode", text)
        self.assertIn("--client jetbrains", text)
        self.assertIn("install.py", text)

    def test_install_help_has_client_flag(self):
        help_text = _install_help()
        self.assertIn("--client", help_text)
        self.assertIn("warp", help_text)
        self.assertIn("opencode", help_text)
        self.assertIn("jetbrains", help_text)
        self.assertIn("--unregister", help_text)

    def test_prompts_mention_correct_warp_path(self):
        text = PROMPTS_MD.read_text(encoding="utf-8")
        # Warp reads ~/.warp/.mcp.json, NOT ~/.warp/mcp_servers.json
        self.assertIn(".mcp.json", text)
        self.assertNotIn("mcp_servers.json", text)

    def test_prompts_mention_absolute_python(self):
        text = PROMPTS_MD.read_text(encoding="utf-8")
        self.assertIn("absolute path", text.lower())


class TestInstallSelfInstallGuard(unittest.TestCase):
    """Self-install (target == repo of the tool) should not crash on Windows."""

    def test_copy_update_files_skips_self(self):
        # Import install.py as a module and check the guard logic.
        import importlib.util
        spec = importlib.util.spec_from_file_location("install_test", str(INSTALL_PY))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        from pathlib import Path as P
        here = P(str(INSTALL_PY)).resolve().parent
        # The guard: if src.resolve() == dst.resolve(): continue
        # We can't fully test without a real self-install, but we can verify
        # the function does not raise on src==dst by mocking.
        import tempfile, shutil
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = P(tmp)
            # Create a fake backup dir
            backup = tmp_path / ".backup"
            backup.mkdir()
            # Create a fake UPDATE_PATHS entry that IS here
            # copy_update_files iterates UPDATE_PATHS; we just verify no crash
            # by calling it with target==HERE (the tool's own repo).
            # This is the exact scenario from the Warp feedback.
            try:
                mod.copy_update_files(here, backup)
            except OSError as e:
                self.fail(f"copy_update_files crashed on self-install: {e}")


if __name__ == "__main__":
    unittest.main(verbosity=2)