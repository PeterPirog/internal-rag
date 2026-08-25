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


class TestWindowsAppsStubDetection(unittest.TestCase):
    """The detector must reject the WindowsApps Python stub."""

    def _load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_install_mod", str(INSTALL_PY))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_is_windowsapps_stub_true(self):
        mod = self._load()
        from pathlib import Path
        stub = Path("C:/Users/test/AppData/Local/Microsoft/WindowsApps/python.exe")
        self.assertTrue(mod._is_windowsapps_stub(stub))

    def test_is_windowsapps_stub_false_for_real_python(self):
        mod = self._load()
        from pathlib import Path
        real = Path("C:/Python312/python.exe")
        self.assertFalse(mod._is_windowsapps_stub(real))

    def test_detect_python_returns_verified_path(self):
        """detect_python must return a path that actually works with --version."""
        mod = self._load()
        py = mod.detect_python()
        import subprocess
        r = subprocess.run([py, "--version"], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(r.returncode, 0)
        self.assertIn(b"Python", r.stdout + r.stderr)


class TestUnregisterCleanup(unittest.TestCase):
    """--unregister must remove empty config files + parent dirs."""

    def setUp(self):
        import tempfile, shutil
        self.tmp = Path(tempfile.mkdtemp(prefix="irag-unreg-"))
        (self.tmp / ".git").mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_install_mod2", str(INSTALL_PY))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_unregister_removes_empty_warp_config(self):
        import json
        mod = self._load()
        warp_dir = self.tmp / ".warp"
        warp_dir.mkdir()
        cfg = warp_dir / ".mcp.json"
        cfg.write_text(json.dumps({"mcpServers": {
            "mcp-light-memory": {"command": "python", "args": ["x"]}
        }}), encoding="utf-8")
        mod.unregister_client("warp", self.tmp, False, "mcp-light-memory")
        self.assertFalse(cfg.exists(), "config file should be deleted when empty")
        self.assertFalse(warp_dir.exists(), ".warp/ dir should be deleted when empty")

    def test_unregister_keeps_config_if_other_servers(self):
        import json
        mod = self._load()
        warp_dir = self.tmp / ".warp"
        warp_dir.mkdir()
        cfg = warp_dir / ".mcp.json"
        cfg.write_text(json.dumps({"mcpServers": {
            "mcp-light-memory": {"command": "python", "args": ["x"]},
            "other-server": {"command": "node", "args": ["y"]}
        }}), encoding="utf-8")
        mod.unregister_client("warp", self.tmp, False, "mcp-light-memory")
        self.assertTrue(cfg.exists(), "config should remain (other server present)")
        data = json.loads(cfg.read_text(encoding="utf-8"))
        self.assertNotIn("mcp-light-memory", data["mcpServers"])
        self.assertIn("other-server", data["mcpServers"])


if __name__ == "__main__":
    unittest.main(verbosity=2)