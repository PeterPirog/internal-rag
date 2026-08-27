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
        """V2 uses Plugin.define({ id, async setup(ctx) }) — NOT the V1 hooks-object API."""
        import re
        src = self._plugin_src("internal-rag-resilience-v2.ts")
        self.assertIn("Plugin.define", src, "V2 must use Plugin.define")
        self.assertIn("mcp-light-memory.resilience", src, "stable plugin id")
        # must import the runtime Plugin (value import, not just the type)
        self.assertRegex(src, r"import\s*\{\s*Plugin\s*\}\s*from\s*\"@opencode-ai/plugin\"")
        # setup must be async (awaited hook registrations)
        self.assertRegex(src, r"async\s+setup\s*\(",
                         "setup must be async to await hook registrations")
        # must await ctx.tool.hook("execute.after", ...) — not fire-and-forget
        self.assertRegex(
            src,
            r"await\s+ctx\.tool\.hook\s*\(\s*[\"']execute\.after[\"']",
            "V2 must await ctx.tool.hook(\"execute.after\", ...)")
        # must subscribe to the public event stream via ctx.event.subscribe({signal})
        self.assertRegex(
            src,
            r"ctx\.event\.subscribe\s*\(\s*\{\s*signal\s*:",
            "V2 must receive public events via ctx.event.subscribe({ signal })")

    def test_v2_plugin_is_not_v1_hooks_object(self):
        """V2 must NOT be the V1 hooks-object shape; must NOT use the
        undocumented V1 experimental hook; must NOT register the public event
        names as SessionHooks (they are not in the documented SessionHooks)."""
        import re
        src = self._plugin_src("internal-rag-resilience-v2.ts")
        # The V1 shape is a returned object keyed by the dotted hook name.
        self.assertNotIn('"tool.execute.after":', src,
                          "V2 must not use the V1 hooks-object 'tool.execute.after' key")
        self.assertNotIn("experimental.session.compacting", src,
                         "V2 must not copy the undocumented-for-V2 experimental hook")
        # session.error/session.idle/session.compacted are public EVENTS, not
        # SessionHook names (documented SessionHooks: context, model.request,
        # http.request, http.response). They MUST NOT be passed to
        # ctx.session.hook(...).
        for fake_session_hook in ("session.error", "session.idle", "session.compacted"):
            pattern = r"ctx\.session\.hook\s*\(\s*[\"']" + re.escape(fake_session_hook)
            self.assertNotRegex(
                src, pattern,
                f"V2 must not register '{fake_session_hook}' via ctx.session.hook "
                "(it is a public event, not a SessionHook name)")

    def test_v2_plugin_no_silent_empty_catch(self):
        """V2 must not use empty `catch {}` blocks — failures must be logged."""
        import re
        src = self._plugin_src("internal-rag-resilience-v2.ts")
        empty_catches = re.findall(r"catch\s*(?:\([^)]*\))?\s*\{\s*\}", src)
        self.assertEqual([], empty_catches,
                         "V2 plugin has silent empty catch blocks (failures swallowed)")

    def test_v2_plugin_cleanup_aborts_event_stream(self):
        """The cleanup returned by setup must abort the event-stream
        AbortController (not a fake subprocess cancellation)."""
        import re
        src = self._plugin_src("internal-rag-resilience-v2.ts")
        # An AbortController must be created for the event stream and aborted
        # in the cleanup closure.
        self.assertRegex(src, r"new\s+AbortController\s*\(\s*\)",
                         "V2 must create an AbortController for the event stream")
        # The cleanup must call .abort() on it.
        self.assertRegex(src, r"\.abort\s*\(\s*\)",
                         "V2 cleanup must abort the event-stream AbortController")
        # The event stream subscription must pass the controller's signal.
        self.assertRegex(src, r"signal\s*:\s*\w+\.signal",
                         "V2 must pass the AbortController signal to ctx.event.subscribe")

    def test_v2_plugin_disposes_only_real_registrations(self):
        """The cleanup must dispose only awaited Registration objects, not
        Promise<Registration> (which would be a no-op)."""
        import re
        src = self._plugin_src("internal-rag-resilience-v2.ts")
        # registrations must be typed/pushed as Registration, and the result of
        # `await ctx.tool.hook(...)` must be pushed (not the Promise itself).
        self.assertRegex(src, r"await\s+ctx\.tool\.hook",
                         "V2 must await the tool hook before pushing to registrations")
        # The dispose call must handle a Promise return (Registration.dispose
        # returns Promise<void> per the docs).
        self.assertRegex(src, r"\.dispose\s*\?\s*\.",
                         "V2 cleanup must call dispose() on registrations")

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


class TestFailClosedConfigHandling(unittest.TestCase):
    """A malformed existing client config must NEVER be overwritten.

    The installer must fail with a clear ERROR (path + parser error) and
    leave the file byte-for-byte unchanged.
    """

    def setUp(self):
        import tempfile, shutil
        self.tmp = Path(tempfile.mkdtemp(prefix="irag-failclosed-"))
        (self.tmp / ".git").mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_install_fc", str(INSTALL_PY))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _malformed_warp_cfg(self) -> Path:
        d = self.tmp / ".warp"
        d.mkdir()
        cfg = d / ".mcp.json"
        cfg.write_text('{"mcpServers": {"broken": { ... trailing garbage,}\n', encoding="utf-8")
        return cfg

    def test_malformed_warp_config_unchanged(self):
        mod = self._load()
        cfg = self._malformed_warp_cfg()
        before = cfg.read_bytes()
        with self.assertRaises(SystemExit):
            mod.register_client("warp", self.tmp, False, "mcp-light-memory",
                                ".agents/skills/internal-rag/mlm.py", ["mcp"])
        self.assertEqual(cfg.read_bytes(), before,
                         "malformed Warp config was modified by the installer")

    def test_malformed_warp_error_is_clear(self):
        mod = self._load()
        cfg = self._malformed_warp_cfg()
        import io, contextlib
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stdout(buf):
            mod.register_client("warp", self.tmp, False, "mcp-light-memory",
                                ".agents/skills/internal-rag/mlm.py", ["mcp"])
        out = buf.getvalue()
        self.assertIn("ERROR", out)
        self.assertIn(str(cfg), out)
        self.assertIn("parser error", out)

    def test_malformed_opencode_config_unchanged(self):
        mod = self._load()
        cfg = self.tmp / "opencode.json"
        cfg.write_text('{"mcp": "not-an-object"', encoding="utf-8")
        before = cfg.read_bytes()
        with self.assertRaises(SystemExit):
            mod.register_client("opencode", self.tmp, False, "mcp-light-memory",
                                ".agents/skills/internal-rag/mlm.py", ["mcp"])
        self.assertEqual(cfg.read_bytes(), before,
                         "malformed OpenCode config was modified by the installer")

    def test_malformed_opencode2_config_unchanged(self):
        mod = self._load()
        cfg = self.tmp / "opencode.json"
        cfg.write_text('{"mcp": {"servers": [1,2,3]', encoding="utf-8")
        before = cfg.read_bytes()
        with self.assertRaises(SystemExit):
            mod.register_client("opencode2", self.tmp, False, "mcp-light-memory",
                                ".agents/skills/internal-rag/mlm.py", ["mcp"])
        self.assertEqual(cfg.read_bytes(), before,
                         "malformed OpenCode2 config was modified by the installer")

    def test_valid_config_still_merge_preserved(self):
        """Valid existing configs must still be merged, not clobbered."""
        import json
        mod = self._load()
        cfg = self.tmp / ".warp" / ".mcp.json"
        cfg.parent.mkdir()
        cfg.write_text(json.dumps({
            "mcpServers": {"other-server": {"command": "node", "args": ["x"]}}
        }), encoding="utf-8")
        mod.register_client("warp", self.tmp, False, "mcp-light-memory",
                            ".agents/skills/internal-rag/mlm.py", ["mcp"])
        data = json.loads(cfg.read_text(encoding="utf-8"))
        self.assertIn("other-server", data["mcpServers"])
        self.assertIn("mcp-light-memory", data["mcpServers"])

    def test_load_client_config_missing_file_is_empty(self):
        mod = self._load()
        self.assertEqual(mod.load_client_config(self.tmp / "nope.json"), {})

    def test_load_client_config_rejects_non_object_top_level(self):
        mod = self._load()
        cfg = self.tmp / "oc.json"
        cfg.write_text("[1, 2, 3]", encoding="utf-8")
        with self.assertRaises(mod.ConfigParseError):
            mod.load_client_config(cfg)
        self.assertEqual(cfg.read_bytes(), b"[1, 2, 3]",
                         "unreadable shape must leave the file untouched")


class TestOpenCodeJsoncSafePath(unittest.TestCase):
    """OpenCode officially supports JSONC. The installer must not guess at
    rewriting a JSONC file: when only opencode.jsonc exists (no .json), the
    automatic write path is ambiguous -> fail safely with precise manual
    instructions instead of risking config loss."""

    def setUp(self):
        import tempfile, shutil
        self.tmp = Path(tempfile.mkdtemp(prefix="irag-jsonc-"))
        (self.tmp / ".git").mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_install_jsonc", str(INSTALL_PY))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_resolve_prefers_json_when_present(self):
        mod = self._load()
        (self.tmp / "opencode.json").write_text("{}", encoding="utf-8")
        (self.tmp / "opencode.jsonc").write_text("{}", encoding="utf-8")
        path, manual = mod.resolve_opencode_config(self.tmp, False)
        self.assertFalse(manual)
        self.assertEqual(path.name, "opencode.json")

    def test_resolve_manual_when_only_jsonc_exists(self):
        mod = self._load()
        (self.tmp / "opencode.jsonc").write_text("// comment\n{}", encoding="utf-8")
        path, manual = mod.resolve_opencode_config(self.tmp, False)
        self.assertTrue(manual)
        self.assertEqual(path.name, "opencode.json")

    def test_register_fails_safe_on_jsonc_only(self):
        import io, contextlib
        mod = self._load()
        jsonc = self.tmp / "opencode.jsonc"
        jsonc.write_text("// my comment\n{\"mcp\": {}}", encoding="utf-8")
        before = jsonc.read_bytes()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = mod.register_client("opencode", self.tmp, False,
                                         "mcp-light-memory",
                                         ".agents/skills/internal-rag/mlm.py",
                                         ["mcp"])
        self.assertEqual(result.status, "MANUAL_REQUIRED")
        self.assertIsNone(result.cfg_path)
        self.assertEqual(jsonc.read_bytes(), before,
                         "JSONC config must remain byte-for-byte unchanged")
        out = buf.getvalue()
        self.assertIn("MANUAL EDIT REQUIRED (JSONC)", out)
        self.assertIn(str(jsonc), out)
        self.assertNotIn("mcp-light-memory", jsonc.read_text(encoding="utf-8"))

    def test_jsonc_plus_compaction_does_not_create_opencode_json(self):
        """--compaction with a JSONC-only setup must NOT implicitly create a
        second opencode.json file next to the user's opencode.jsonc."""
        import io, contextlib
        mod = self._load()
        jsonc = self.tmp / "opencode.jsonc"
        jsonc.write_text("// comment\n{}", encoding="utf-8")
        before = jsonc.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            mod.integrate_compaction("opencode", self.tmp, False)
        self.assertFalse((self.tmp / "opencode.json").exists(),
                         "compaction must not create a second config file next to JSONC")
        self.assertEqual(jsonc.read_bytes(), before,
                         "JSONC must remain byte-for-byte unchanged")


class TestClientConfigPaths(unittest.TestCase):
    """Warp/OpenCode/OpenCode2 project vs global config path contract."""

    def _load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_install_paths", str(INSTALL_PY))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_warp_project_and_global_paths(self):
        mod = self._load()
        from pathlib import Path as P
        project = P("/tmp/proj")
        self.assertEqual(mod.client_config_path("warp", project, False),
                         project / ".warp" / ".mcp.json")
        self.assertEqual(mod.client_config_path("warp", project, True),
                         P.home() / ".warp" / ".mcp.json")

    def test_opencode_project_and_global_paths(self):
        mod = self._load()
        from pathlib import Path as P
        project = P("/tmp/proj")
        self.assertEqual(mod.client_config_path("opencode", project, False),
                         project / "opencode.json")
        self.assertEqual(mod.client_config_path("opencode", project, True),
                         P.home() / ".config" / "opencode" / "opencode.json")

    def test_opencode2_project_and_global_paths(self):
        mod = self._load()
        from pathlib import Path as P
        project = P("/tmp/proj")
        self.assertEqual(mod.client_config_path("opencode2", project, False),
                         project / "opencode.json")
        self.assertEqual(mod.client_config_path("opencode2", project, True),
                         P.home() / ".config" / "opencode" / "opencode.json")


class TestJetbrainsScopeInstructions(unittest.TestCase):
    """JetBrains: --client jetbrains prints Project level; --global prints
    Global level. No config file is ever written automatically."""

    def setUp(self):
        import tempfile, shutil
        self.tmp = Path(tempfile.mkdtemp(prefix="irag-jb-"))
        (self.tmp / ".git").mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_install_jb", str(INSTALL_PY))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _capture(self, fn):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = fn()
        return buf.getvalue(), result

    def test_project_mode_prints_project_level(self):
        mod = self._load()
        out, result = self._capture(lambda: mod.register_client(
            "jetbrains", self.tmp, False, "mcp-light-memory",
            ".agents/skills/internal-rag/mlm.py", ["mcp"]))
        self.assertEqual(result.status, "INSTRUCTIONS_ONLY",
                         "JetBrains must report INSTRUCTIONS_ONLY (never REGISTERED)")
        self.assertIn("Server level: Project / Current project.", out)
        self.assertNotIn("Server level: Global (all projects).", out)

    def test_global_mode_prints_global_level(self):
        mod = self._load()
        out, result = self._capture(lambda: mod.register_client(
            "jetbrains", self.tmp, True, "mcp-light-memory",
            ".agents/skills/internal-rag/mlm.py", ["mcp"]))
        self.assertEqual(result.status, "INSTRUCTIONS_ONLY")
        self.assertIn("Server level: Global (all projects).", out)
        self.assertNotIn("Server level: Project / Current project.", out)

    def test_never_writes_jetbrains_config_file(self):
        mod = self._load()
        for global_cfg in (False, True):
            before = sorted(p.name for p in self.tmp.rglob("*"))
            self._capture(lambda: mod.register_client(
                "jetbrains", self.tmp, global_cfg, "mcp-light-memory",
                ".agents/skills/internal-rag/mlm.py", ["mcp"]))
            after = sorted(p.name for p in self.tmp.rglob("*"))
            self.assertEqual(before, after,
                             "installer must not create/modify files for JetBrains")


class TestRegistrationOutcomeReporting(unittest.TestCase):
    """register_client() must return an explicit, unambiguous outcome:
    REGISTERED / MANUAL_REQUIRED / INSTRUCTIONS_ONLY — and the output must
    never claim 'registered' when it did not happen."""

    def setUp(self):
        import tempfile, shutil
        self.tmp = Path(tempfile.mkdtemp(prefix="irag-regout-"))
        (self.tmp / ".git").mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("_install_regout", str(INSTALL_PY))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _capture(self, client, **kw):
        import io, contextlib
        mod = self._load()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = mod.register_client(client, self.tmp, kw.get("global_cfg", False),
                                         "mcp-light-memory",
                                         ".agents/skills/internal-rag/mlm.py",
                                         ["mcp"])
        return buf.getvalue(), result

    def test_warp_reports_registered(self):
        out, result = self._capture("warp")
        self.assertEqual(result.status, "REGISTERED")
        self.assertEqual(result.cfg_path, self.tmp / ".warp" / ".mcp.json")
        self.assertIn("Registered MCP server 'mcp-light-memory'", out)

    def test_opencode_json_reports_registered(self):
        out, result = self._capture("opencode")
        self.assertEqual(result.status, "REGISTERED")
        self.assertEqual(result.cfg_path, self.tmp / "opencode.json")

    def test_opencode2_json_reports_registered(self):
        out, result = self._capture("opencode2")
        self.assertEqual(result.status, "REGISTERED")
        self.assertEqual(result.cfg_path, self.tmp / "opencode.json")

    def test_jsonc_only_reports_manual_required_and_never_registered(self):
        (self.tmp / "opencode.jsonc").write_text("// c\n{}", encoding="utf-8")
        out, result = self._capture("opencode")
        self.assertEqual(result.status, "MANUAL_REQUIRED")
        self.assertIn("MANUAL EDIT REQUIRED (JSONC)", out)
        self.assertNotIn("MCP REGISTRATION: REGISTERED", out)
        self.assertNotIn("MCP server registered", out.lower().replace(
            "registered mcp server 'mcp-light-memory'", ""))
        # The installer must not claim a completed MCP registration.
        self.assertNotIn("Registered MCP server", out)

    def test_jetbrains_output_never_says_registered(self):
        out, result = self._capture("jetbrains")
        self.assertEqual(result.status, "INSTRUCTIONS_ONLY")
        low = out.lower()
        self.assertNotIn("registered", low,
                         "JetBrains output must never claim the server is registered")

    def test_malformed_config_byte_for_byte_unchanged(self):
        d = self.tmp / ".warp"
        d.mkdir()
        cfg = d / ".mcp.json"
        bad = b'{"mcpServers": {"x": { broken, }\n'
        cfg.write_bytes(bad)
        with self.assertRaises(SystemExit):
            self._capture("warp")
        self.assertEqual(cfg.read_bytes(), bad)

    def test_main_jsonc_path_exits_2_and_never_claims_registered(self):
        """End-to-end: main() with a JSONC-only OpenCode setup must exit 2,
        print the manual-action block, and never print a success/registered
        message for the MCP step."""
        import subprocess
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "config", "user.name", "t"], check=True)
        (self.tmp / "app.py").write_text("print(1)\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.tmp), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.tmp), "commit", "-q", "-m", "init"], check=True)
        (self.tmp / "opencode.jsonc").write_text("// c\n{}", encoding="utf-8")
        r = subprocess.run([sys.executable, str(INSTALL_PY), str(self.tmp),
                            "--client", "opencode"],
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 2,
                         f"MANUAL_REQUIRED must exit 2, got {r.returncode}\n{r.stdout}\n{r.stderr}")
        out = r.stdout
        self.assertIn("PROJECT FILES INSTALLED", out)
        self.assertIn("MCP REGISTRATION NOT COMPLETE", out)
        self.assertIn("MANUAL ACTION REQUIRED", out)
        self.assertIn("MCP REGISTRATION: MANUAL_REQUIRED", out)
        self.assertNotIn("INSTALLATION COMPLETE\nMCP server registered", out)
        self.assertNotIn("MCP server registered for", out)
        self.assertIn("MCP REGISTRATION", out)


class TestInstallPs1Parity(unittest.TestCase):
    """install.ps1 must accept the same functional flags as install.py:
    --client, --global, --compaction, --server-name, --unregister,
    --share-tools (passed through to install.py)."""

    def test_ps1_exposes_all_flags(self):
        text = (PROJECT_ROOT / "install.ps1").read_text(encoding="utf-8")
        for flag in ("$Client", "$Global", "$Compaction", "$ServerName",
                     "$Unregister", "$ShareTools"):
            self.assertIn(flag, text, f"install.ps1 missing parameter {flag}")
        for passthrough in ("--client", "--global", "--compaction",
                            "--server-name", "--unregister", "--share-tools"):
            self.assertIn(passthrough, text, f"install.ps1 missing {passthrough} passthrough")

    def test_ps1_client_is_validated(self):
        text = (PROJECT_ROOT / "install.ps1").read_text(encoding="utf-8")
        self.assertIn("ValidateSet", text,
                      "install.ps1 should constrain -Client to known clients")
        for client in ("warp", "opencode", "opencode2", "jetbrains"):
            self.assertIn(client, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)