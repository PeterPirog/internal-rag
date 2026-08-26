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
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    return p.stdout.decode("utf-8", errors="replace")
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
        self.assertIn("opencode2", help_text)
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


class TestOpenCodeV1V2Split(unittest.TestCase):
    """OpenCode 1 (stable) vs OpenCode 2 (beta) config structure.

    Per official docs (https://opencode.ai/docs/mcp-servers/ + /docs/config):
      - OpenCode 1 (stable): mcp.<name> FLAT (no "servers" sub-key), enabled: true
      - OpenCode 2 (beta): mcp.servers.<name>, no "enabled" (absent = enabled)
    """

    def setUp(self):
        import tempfile, shutil
        self.tmp = Path(tempfile.mkdtemp(prefix="irag-oc-split-"))
        (self.tmp / ".git").mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_install_oc", str(INSTALL_PY))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_opencode_v1_flat_mcp_with_enabled(self):
        """OpenCode 1 (stable): mcp.<name> FLAT with enabled: true (NO "servers" sub-key)."""
        import json
        mod = self._load()
        mod.register_client("opencode", self.tmp, False, "mcp-light-memory",
                            ".agents/skills/internal-rag/mlm.py", ["mcp"])
        cfg = self.tmp / "opencode.json"
        self.assertTrue(cfg.exists())
        data = json.loads(cfg.read_text(encoding="utf-8"))
        # V1: server is directly under mcp.<name> (FLAT)
        self.assertIn("mcp", data)
        self.assertIn("mcp-light-memory", data["mcp"])
        entry = data["mcp"]["mcp-light-memory"]
        self.assertEqual(entry["type"], "local")
        self.assertIn("enabled", entry)
        self.assertTrue(entry["enabled"])
        self.assertIn("command", entry)
        self.assertIsInstance(entry["command"], list)
        self.assertIn("cwd", entry)
        # V1 does NOT use mcp.servers
        self.assertNotIn("servers", data["mcp"])

    def test_opencode_v2_servers_nested_no_enabled(self):
        """OpenCode 2 (beta): mcp.servers.<name> with no "enabled" field."""
        import json
        mod = self._load()
        mod.register_client("opencode2", self.tmp, False, "mcp-light-memory",
                            ".agents/skills/internal-rag/mlm.py", ["mcp"])
        cfg = self.tmp / "opencode.json"
        self.assertTrue(cfg.exists())
        data = json.loads(cfg.read_text(encoding="utf-8"))
        # V2: server is under mcp.servers.<name>
        self.assertIn("mcp", data)
        self.assertIn("servers", data["mcp"])
        entry = data["mcp"]["servers"]["mcp-light-memory"]
        self.assertEqual(entry["type"], "local")
        self.assertNotIn("enabled", entry)  # V2 does NOT use 'enabled'
        self.assertIn("command", entry)
        self.assertIsInstance(entry["command"], list)
        self.assertIn("cwd", entry)

    def test_opencode_v1_merge_preserves_other_flat_servers(self):
        """V1 merge: existing flat mcp.<name> servers + other config keys preserved."""
        import json
        mod = self._load()
        cfg = self.tmp / "opencode.json"
        cfg.write_text(json.dumps({
            "$schema": "https://opencode.ai/config.json",
            "model": "anthropic/claude-sonnet-4-5",
            "mcp": {"other-mcp": {"type": "remote", "url": "https://x", "enabled": True}}
        }), encoding="utf-8")
        mod.register_client("opencode", self.tmp, False, "mcp-light-memory",
                            ".agents/skills/internal-rag/mlm.py", ["mcp"])
        data = json.loads(cfg.read_text(encoding="utf-8"))
        self.assertIn("other-mcp", data["mcp"])        # original flat server preserved
        self.assertIn("mcp-light-memory", data["mcp"])  # new flat server added
        self.assertEqual(data["model"], "anthropic/claude-sonnet-4-5")
        # No "servers" sub-key introduced
        self.assertNotIn("servers", data["mcp"])

    def test_opencode_v2_merge_preserves_other_nested_servers(self):
        """V2 merge: existing mcp.servers.<name> servers preserved."""
        import json
        mod = self._load()
        cfg = self.tmp / "opencode.json"
        cfg.write_text(json.dumps({
            "$schema": "https://opencode.ai/config.json",
            "mcp": {"servers": {"other-v2": {"type": "remote", "url": "https://y"}}}
        }), encoding="utf-8")
        mod.register_client("opencode2", self.tmp, False, "mcp-light-memory",
                            ".agents/skills/internal-rag/mlm.py", ["mcp"])
        data = json.loads(cfg.read_text(encoding="utf-8"))
        self.assertIn("other-v2", data["mcp"]["servers"])
        self.assertIn("mcp-light-memory", data["mcp"]["servers"])

    def test_opencode_v1_unregister_removes_from_flat_mcp(self):
        """V1 unregister removes from mcp.<name> (flat)."""
        import json
        mod = self._load()
        cfg = self.tmp / "opencode.json"
        cfg.write_text(json.dumps({
            "mcp": {"mcp-light-memory": {"type": "local", "command": ["x"], "enabled": True},
                    "other": {"type": "remote", "url": "http://x"}}
        }), encoding="utf-8")
        mod.unregister_client("opencode", self.tmp, False, "mcp-light-memory")
        data = json.loads(cfg.read_text(encoding="utf-8"))
        self.assertNotIn("mcp-light-memory", data.get("mcp", {}))
        self.assertIn("other", data.get("mcp", {}))  # other server preserved

    def test_opencode_v2_unregister_removes_from_nested_servers(self):
        """V2 unregister removes from mcp.servers.<name>."""
        import json
        mod = self._load()
        cfg = self.tmp / "opencode.json"
        cfg.write_text(json.dumps({
            "mcp": {"servers": {"mcp-light-memory": {"type": "local", "command": ["x"]},
                                "other-v2": {"type": "remote", "url": "http://y"}}}
        }), encoding="utf-8")
        mod.unregister_client("opencode2", self.tmp, False, "mcp-light-memory")
        data = json.loads(cfg.read_text(encoding="utf-8"))
        self.assertNotIn("mcp-light-memory", data.get("mcp", {}).get("servers", {}))
        self.assertIn("other-v2", data.get("mcp", {}).get("servers", {}))

    def test_verify_registered_server_opencode2_command_array(self):
        """_verify_registered_server must handle opencode2 command as array."""
        mod = self._load()
        entry = {
            "type": "local",
            "command": [sys.executable, "/fake/script.py", "mcp"],
            "cwd": "/fake",
        }
        # Should not raise — it runs the first element of the command array
        try:
            mod._verify_registered_server(entry, "opencode2")
        except Exception as e:
            self.fail(f"_verify_registered_server raised on opencode2 array command: {e}")


class TestOpenCodePluginV1V2Select(unittest.TestCase):
    """P2/P3: the installed plugin must match the client, and both plugins
    must use the documented hooks-object API with no silent catch-swallowing."""

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.TemporaryDirectory(prefix="irag-plugin-select-")
        self.tmp = Path(self._tmpdir.name)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self._tmpdir.cleanup()

    def _load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_install_mod_ps", str(INSTALL_PY))
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _plugin_src(self, name):
        return (HERE.parent / ".opencode" / "plugins" / name).read_text(encoding="utf-8")

    def test_v1_plugin_uses_documented_hooks_object_api(self):
        src = self._plugin_src("internal-rag-resilience.ts")
        self.assertIn("@opencode-ai/plugin", src)
        self.assertIn("return {", src)
        self.assertIn('"tool.execute.after"', src)
        self.assertIn('"experimental.session.compacting"', src)

    def test_v2_plugin_uses_v2_runtime_api(self):
        """V2 uses Plugin.define({ id, setup(ctx) }) — NOT the V1 hooks-object API."""
        src = self._plugin_src("internal-rag-resilience-v2.ts")
        self.assertIn("Plugin.define", src, "V2 must use Plugin.define")
        self.assertIn("setup", src, "V2 must define setup(ctx)")
        self.assertIn("ctx.tool.hook(\"execute.after\"", src,
                      "V2 must register ctx.tool.hook(\"execute.after\")")
        # stable plugin id
        self.assertIn("mcp-light-memory.resilience", src)
        # must import the runtime Plugin (value import, not just the type)
        self.assertRegex(src, r"import\s*\{\s*Plugin\s*\}\s*from\s*\"@opencode-ai/plugin\"")

    def test_v2_plugin_is_not_v1_hooks_object(self):
        """V2 must NOT be the V1 hooks-object shape (return { \"tool.execute.after\" ... })."""
        src = self._plugin_src("internal-rag-resilience-v2.ts")
        # The V1 shape is a returned object keyed by the dotted hook name.
        self.assertNotIn('"tool.execute.after":', src,
                         "V2 must not use the V1 hooks-object 'tool.execute.after' key")
        self.assertNotIn("experimental.session.compacting", src,
                         "V2 must not copy the undocumented-for-V2 experimental hook")

    def test_v2_plugin_no_silent_empty_catch(self):
        """V2 must not use empty `catch {}` blocks — failures must be logged."""
        import re
        src = self._plugin_src("internal-rag-resilience-v2.ts")
        empty_catches = re.findall(r"catch\s*(?:\([^)]*\))?\s*\{\s*\}", src)
        self.assertEqual([], empty_catches,
                         "V2 plugin has silent empty catch blocks (failures swallowed)")

    def test_v1_install_copies_v1_removes_v2(self):
        mod = self._load()
        import tempfile, shutil
        # Prepare target with a stale V2 plugin file to prove removal
        v2 = self.tmp / ".opencode" / "plugins" / "internal-rag-resilience-v2.ts"
        v2.parent.mkdir(parents=True)
        v2.write_text("// stale\n", encoding="utf-8")
        backup = self.tmp / "backup"
        backup.mkdir()
        mod.copy_update_files(self.tmp, backup, client="opencode")
        self.assertTrue((self.tmp / ".opencode/plugins/internal-rag-resilience.ts").exists())
        self.assertFalse(v2.exists(), "V2 plugin must be removed for V1 install")

    def test_v2_install_copies_v2_removes_v1(self):
        mod = self._load()
        v1 = self.tmp / ".opencode" / "plugins" / "internal-rag-resilience.ts"
        v1.parent.mkdir(parents=True)
        v1.write_text("// stale\n", encoding="utf-8")
        backup = self.tmp / "backup"
        backup.mkdir()
        mod.copy_update_files(self.tmp, backup, client="opencode2")
        self.assertTrue((self.tmp / ".opencode/plugins/internal-rag-resilience-v2.ts").exists())
        self.assertFalse(v1.exists(), "V1 plugin must be removed for V2 install")

    def test_default_install_copies_v1(self):
        mod = self._load()
        backup = self.tmp / "backup"
        backup.mkdir()
        mod.copy_update_files(self.tmp, backup, client=None)
        self.assertTrue((self.tmp / ".opencode/plugins/internal-rag-resilience.ts").exists())

    def test_self_install_does_not_remove_own_plugins(self):
        """Copying the repo into itself must not delete the repo's own plugins."""
        mod = self._load()
        backup = self.tmp / "backup"
        backup.mkdir()
        here = INSTALL_PY.resolve().parent
        v2 = here / ".opencode" / "plugins" / "internal-rag-resilience-v2.ts"
        self.assertTrue(v2.exists(), "fixture precondition")
        mod.copy_update_files(here, backup, client="opencode")
        # The repo's own V2 file is source and destination — must survive.
        self.assertTrue(v2.exists(), "self-install must not delete the repo's own plugin")


if __name__ == "__main__":
    unittest.main(verbosity=2)