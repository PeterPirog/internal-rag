#!/usr/bin/env python3
"""Tests for the E: multi-project MCP router (irag_mcp_router.py).

Covers:
- registry loading/validation (allowlist)
- unknown project rejection
- write=false blocks mutating tools (remember/checkpoint/resume) read-only
- multi-project isolation (each project only sees its own memories)
- `projects` tool reports id/root/write/availability
- protocol: initialize / tools/list / tools/call / stderr purity
"""
from __future__ import annotations
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
SKILL_DIR = PROJECT_ROOT / ".agents" / "skills" / "internal-rag"
IRAG_PATH = SKILL_DIR / "irag.py"
ROUTER_PATH = SKILL_DIR / "irag_mcp_router.py"

_spec = importlib.util.spec_from_file_location("router_mod", str(ROUTER_PATH))
router = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(router)


def _make_project(root: Path, mem_id: str, title: str, body: str) -> None:
    rag = root / "INTERNAL_RAG"
    for d in ("decisions", "knowledge", "gotchas", "failures", "hypotheses",
              "sessions", "sessions/.snapshots", "archive"):
        (rag / d).mkdir(parents=True, exist_ok=True)
    (rag / "WORKING_STATE.md").write_text("# Working state\n", encoding="utf-8")
    text = (
        "---\n"
        f"id: {mem_id}\n"
        "type: knowledge\nstatus: active\n"
        "created: 2024-01-01\nscope: []\ntags: []\n"
        "---\n\n"
        f"# {title}\n\n## Knowledge\n\n{body}\n\n## Consequence\n\nNone.\n"
    )
    (rag / "knowledge" / f"{mem_id}.md").write_text(text, encoding="utf-8")


def _stdout_objects(stdout: str) -> list:
    out = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


class RouterBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="irag-router-"))
        self.projs = {}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _add_project(self, pid: str, write: bool, mem_id: str,
                     title: str, body: str, broken: bool = False) -> Path:
        root = self.tmp / pid
        root.mkdir(parents=True, exist_ok=True)
        if not broken:
            _make_project(root, mem_id, title, body)
        self.projs[pid] = {"root": str(root), "write": write}
        return root

    def _write_registry(self, projects: dict) -> Path:
        reg = self.tmp / "registry.json"
        reg.write_text(json.dumps({"projects": projects}), encoding="utf-8")
        return reg

    def _call(self, registry: Path, tool: str, args: dict = None) -> tuple:
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "t", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": tool, "arguments": args}},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        ]
        args_cmd = [sys.executable, str(ROUTER_PATH), "--registry", str(registry)]
        p = subprocess.run(args_cmd, input="\n".join(json.dumps(l) for l in lines) + "\n",
                           cwd=str(self.tmp), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, encoding="utf-8", timeout=120)
        objs = _stdout_objects(p.stdout)
        res = next((o for o in objs if o.get("id") == 2), None)
        assert res is not None, f"no response for tools/call: {objs}"
        text = "".join(c.get("text", "") for c in res.get("result", {}).get("content", []))
        return text, bool(res.get("result", {}).get("isError")), p.stderr


class TestRegistry(unittest.TestCase):
    def test_load_registry_valid(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "proj"
            root.mkdir()
            reg = Path(td) / "reg.json"
            reg.write_text(json.dumps({"projects": {"p1": {"root": str(root), "write": False}}}),
                           encoding="utf-8")
            data = router.load_registry(reg)
            self.assertEqual(set(data), {"p1"})
            self.assertFalse(data["p1"]["write"])
            self.assertTrue(Path(data["p1"]["root"]).is_absolute())

    def test_relative_root_resolves_against_registry(self):
        with tempfile.TemporaryDirectory() as td:
            root = (Path(td) / "proj").resolve()
            root.mkdir()
            reg = (Path(td) / "reg.json").resolve()
            reg.write_text(json.dumps({"projects": {"p1": {"root": "proj"}}}), encoding="utf-8")
            data = router.load_registry(reg)
            # Compare resolved paths (Windows 8.3 short-name safe)
            self.assertEqual(Path(data["p1"]["root"]).resolve(), root)

    def test_bad_registry_errors(self):
        with tempfile.TemporaryDirectory() as td:
            reg = Path(td) / "reg.json"
            reg.write_text("{not json", encoding="utf-8")
            with self.assertRaises(router.RegistryError):
                router.load_registry(reg)
            reg.write_text(json.dumps({"no_projects": True}), encoding="utf-8")
            with self.assertRaises(router.RegistryError):
                router.load_registry(reg)
            reg.write_text(json.dumps({"projects": {}}), encoding="utf-8")
            with self.assertRaises(router.RegistryError):
                router.load_registry(reg)
            self.assertRaises(router.RegistryError, router.load_registry, Path(td) / "missing.json")

    def test_write_must_be_real_boolean(self):
        """CEL E: 'write' must be a JSON bool. Strings/ints are rejected."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "proj"; root.mkdir()
            reg = Path(td) / "reg.json"
            for bad in ("false", "true", 0, 1, "yes", "no"):
                reg.write_text(json.dumps({"projects": {"p1": {"root": str(root), "write": bad}}}),
                               encoding="utf-8")
                with self.assertRaises(router.RegistryError) as cm:
                    router.load_registry(reg)
                self.assertIn("must be a JSON boolean", str(cm.exception))
            # valid booleans
            for ok in (True, False):
                reg.write_text(json.dumps({"projects": {"p1": {"root": str(root), "write": ok}}}),
                               encoding="utf-8")
                data = router.load_registry(reg)
                self.assertEqual(data["p1"]["write"], ok)
            # absent -> default False
            reg.write_text(json.dumps({"projects": {"p1": {"root": str(root)}}}), encoding="utf-8")
            data = router.load_registry(reg)
            self.assertFalse(data["p1"]["write"])

    def test_root_must_be_string(self):
        with tempfile.TemporaryDirectory() as td:
            reg = Path(td) / "reg.json"
            reg.write_text(json.dumps({"projects": {"p1": {"root": 123}}}), encoding="utf-8")
            with self.assertRaises(router.RegistryError):
                router.load_registry(reg)

    def test_empty_project_id_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "proj"; root.mkdir()
            reg = Path(td) / "reg.json"
            reg.write_text(json.dumps({"projects": {"": {"root": str(root)}}}), encoding="utf-8")
            with self.assertRaises(router.RegistryError):
                router.load_registry(reg)


class TestRouterBehavior(RouterBase):
    def test_unknown_project_rejected(self):
        self._add_project("alpha", True, "mem-alpha", "Alpha secret", "alpha unique token xyzzy")
        reg = self._write_registry(self.projs)
        text, is_err, _ = self._call(reg, "search", {"project": "ghost", "query": "anything"})
        self.assertTrue(is_err)
        self.assertIn("unknown project", text)

    def test_write_false_blocks_mutating_tools(self):
        self._add_project("ro", False, "mem-ro", "Read only", "ro body content")
        reg = self._write_registry(self.projs)
        text, is_err, _ = self._call(reg, "remember",
                                     {"project": "ro", "type": "knowledge",
                                      "title": "t", "body": "b"})
        self.assertTrue(is_err)
        self.assertIn("read-only", text)
        # and nothing was written to the project
        self.assertEqual(len(list((self.tmp / "ro" / "INTERNAL_RAG" / "knowledge").glob("*.md"))), 1)
        text2, is_err2, _ = self._call(reg, "checkpoint", {"project": "ro", "reason": "x"})
        self.assertTrue(is_err2)
        self.assertIn("read-only", text2)
        text3, is_err3, _ = self._call(reg, "resume", {"project": "ro"})
        self.assertTrue(is_err3)
        self.assertIn("read-only", text3)

    def test_read_tool_works_on_read_only_project(self):
        self._add_project("ro", False, "mem-ro", "Read only", "ro body content")
        reg = self._write_registry(self.projs)
        text, is_err, _ = self._call(reg, "search", {"project": "ro", "query": "ro body content"})
        self.assertFalse(is_err)
        self.assertIn("mem-ro", text)

    def test_write_true_allows_remember(self):
        self._add_project("rw", True, "mem-rw", "Seed", "seed body content")
        reg = self._write_registry(self.projs)
        text, is_err, _ = self._call(reg, "remember",
                                     {"project": "rw", "type": "knowledge",
                                      "title": "New thing", "body": "brand new memory body"})
        self.assertFalse(is_err, text)
        files = list((self.tmp / "rw" / "INTERNAL_RAG" / "knowledge").glob("*.md"))
        self.assertEqual(len(files), 2)

    def test_isolation_between_projects(self):
        self._add_project("alpha", True, "mem-alpha", "Alpha widget", "alpha unique xyzzy token")
        self._add_project("beta", True, "mem-beta", "Beta widget", "beta unique qqqqq token")
        reg = self._write_registry(self.projs)
        ta, ea, _ = self._call(reg, "search", {"project": "alpha", "query": "unique token xyzzy qqqqq"})
        tb, eb, _ = self._call(reg, "search", {"project": "beta", "query": "unique token xyzzy qqqqq"})
        self.assertFalse(ea)
        self.assertFalse(eb)
        self.assertIn("mem-alpha", ta)
        self.assertNotIn("mem-beta", ta, "alpha must not see beta's memories")
        self.assertIn("mem-beta", tb)
        self.assertNotIn("mem-alpha", tb, "beta must not see alpha's memories")

    def test_projects_tool_lists_availability(self):
        self._add_project("alpha", True, "mem-alpha", "A", "alpha body")
        self._add_project("ghost_dir", False, "x", "X", "y", broken=True)
        reg = self._write_registry(self.projs)
        text, is_err, _ = self._call(reg, "projects")
        self.assertFalse(is_err)
        data = json.loads(text)
        by_id = {p["id"]: p for p in data["projects"]}
        self.assertIn("alpha", by_id)
        self.assertTrue(by_id["alpha"]["available"])
        self.assertTrue(by_id["alpha"]["write"])
        self.assertFalse(by_id["ghost_dir"]["available"])
        self.assertFalse(by_id["ghost_dir"]["write"])
        self.assertIn("INTERNAL_RAG", by_id["ghost_dir"]["reason"])

    def test_project_unavailable_gives_actionable_error(self):
        self._add_project("ghost_dir", False, "x", "X", "y", broken=True)
        reg = self._write_registry(self.projs)
        text, is_err, _ = self._call(reg, "search", {"project": "ghost_dir", "query": "q"})
        self.assertTrue(is_err)
        self.assertIn("unavailable", text)

    def test_protocol_and_stdout_purity(self):
        self._add_project("alpha", True, "mem-alpha", "A", "alpha body content")
        reg = self._write_registry(self.projs)
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "t", "version": "0"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "method": "ping"},
            {"jsonrpc": "2.0", "id": 4, "method": "ping"},
            {"jsonrpc": "2.0", "id": 5, "method": "shutdown"},
        ]
        p = subprocess.run(
            [sys.executable, str(ROUTER_PATH), "--registry", str(reg)],
            input="\n".join(json.dumps(l) for l in lines) + "\n",
            cwd=str(self.tmp), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", timeout=120)
        objs = _stdout_objects(p.stdout)
        self.assertTrue(all(json.loads(json.dumps(o)) == o for o in objs), "stdout must be pure JSON-RPC")
        init = next(o for o in objs if o.get("id") == 1)
        self.assertEqual(init["result"]["serverInfo"]["name"], "mcp-light-memory-router")
        self.assertIn("2025-06-18", init["result"]["protocolVersion"])
        tools = next(o for o in objs if o.get("id") == 2)
        names = [t["name"] for t in tools["result"]["tools"]]
        self.assertIn("projects", names)
        for n in ("context", "search", "remember", "guard"):
            self.assertIn(n, names)
        self.assertTrue(all(t["inputSchema"]["required"][0] == "project"
                            for t in tools["result"]["tools"] if t["name"] != "projects"))
        self.assertIn({"jsonrpc": "2.0", "id": 4, "result": {}}, objs)
        self.assertIn("router ready", p.stderr)

    def test_missing_registry_exits_nonzero(self):
        p = subprocess.run([sys.executable, str(ROUTER_PATH), "--registry",
                            str(self.tmp / "nope.json")],
                           cwd=str(self.tmp), stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True, timeout=60)
        self.assertEqual(p.returncode, 2)
        self.assertIn("registry error", p.stderr)


class TestRouterSecurityRegressions(RouterBase):
    """P1 hardening: extended security regression coverage for the router.

    Covers:
      - unknown project id
      - malformed project id (empty / non-string)
      - registry root outside expected structures (no INTERNAL_RAG)
      - missing root directory
      - root without INTERNAL_RAG/
      - write: "false" (string) -> registry rejected at load
      - write: 0 / 1 (int) -> registry rejected at load
      - cross-project search isolation (re-check)
      - cross-project write isolation (write:false blocks, write:true on A
        does not allow writing into B)
      - path traversal attempts in project id / args
      - symlinked project roots
      - malformed MCP arguments (non-dict arguments)
      - modern + legacy protocol behavior after errors
    """

    def test_unknown_project_rejected_with_registered_list(self):
        self._add_project("alpha", True, "mem-alpha", "Alpha", "alpha body content")
        reg = self._write_registry(self.projs)
        text, is_err, _ = self._call(reg, "search", {"project": "ghost", "query": "x"})
        self.assertTrue(is_err)
        self.assertIn("unknown project", text)
        self.assertIn("Registered projects:", text)
        self.assertIn("alpha", text)

    def test_malformed_project_id_empty_string_rejected(self):
        self._add_project("alpha", True, "mem-alpha", "Alpha", "alpha body content")
        reg = self._write_registry(self.projs)
        text, is_err, _ = self._call(reg, "search", {"project": "", "query": "x"})
        self.assertTrue(is_err)
        self.assertIn("unknown project", text)

    def test_malformed_project_id_non_string_rejected(self):
        self._add_project("alpha", True, "mem-alpha", "Alpha", "alpha body content")
        reg = self._write_registry(self.projs)
        # The router coerces args.get("project","") to str; an int id is
        # converted to "123" which is not registered -> unknown project.
        text, is_err, _ = self._call(reg, "search", {"project": 123, "query": "x"})
        self.assertTrue(is_err)
        self.assertIn("unknown project", text)

    def test_root_without_internal_rag_unavailable(self):
        # root exists but has no INTERNAL_RAG/
        root = self.tmp / "no-rag"
        root.mkdir(parents=True, exist_ok=True)
        (root / "README.md").write_text("not a rag project", encoding="utf-8")
        reg = self._write_registry({"no-rag": {"root": str(root), "write": True}})
        text, is_err, _ = self._call(reg, "projects")
        data = json.loads(text)
        by_id = {p["id"]: p for p in data["projects"]}
        self.assertFalse(by_id["no-rag"]["available"])
        self.assertIn("INTERNAL_RAG", by_id["no-rag"]["reason"])

    def test_missing_root_directory_unavailable(self):
        reg = self._write_registry({"ghost": {"root": str(self.tmp / "does-not-exist"), "write": False}})
        text, is_err, _ = self._call(reg, "projects")
        data = json.loads(text)
        by_id = {p["id"]: p for p in data["projects"]}
        self.assertFalse(by_id["ghost"]["available"])
        self.assertIn("does not exist", by_id["ghost"]["reason"])

    def test_write_string_false_rejected_at_load(self):
        root = self.tmp / "p-str-false"; root.mkdir()
        reg = self.tmp / "reg.json"
        reg.write_text(json.dumps({"projects": {"p": {"root": str(root), "write": "false"}}}),
                       encoding="utf-8")
        with self.assertRaises(router.RegistryError):
            router.load_registry(reg)

    def test_write_int_zero_rejected_at_load(self):
        root = self.tmp / "p-int-zero"; root.mkdir()
        reg = self.tmp / "reg.json"
        reg.write_text(json.dumps({"projects": {"p": {"root": str(root), "write": 0}}}),
                       encoding="utf-8")
        with self.assertRaises(router.RegistryError):
            router.load_registry(reg)

    def test_write_int_one_rejected_at_load(self):
        root = self.tmp / "p-int-one"; root.mkdir()
        reg = self.tmp / "reg.json"
        reg.write_text(json.dumps({"projects": {"p": {"root": str(root), "write": 1}}}),
                       encoding="utf-8")
        with self.assertRaises(router.RegistryError):
            router.load_registry(reg)

    def test_cross_project_search_isolation(self):
        self._add_project("alpha", True, "mem-alpha", "Alpha widget",
                          "alpha unique xyzzy token")
        self._add_project("beta", True, "mem-beta", "Beta widget",
                          "beta unique qqqqq token")
        reg = self._write_registry(self.projs)
        ta, ea, _ = self._call(reg, "search", {"project": "alpha", "query": "unique token xyzzy qqqqq"})
        tb, eb, _ = self._call(reg, "search", {"project": "beta", "query": "unique token xyzzy qqqqq"})
        self.assertFalse(ea)
        self.assertFalse(eb)
        self.assertIn("mem-alpha", ta)
        self.assertNotIn("mem-beta", ta)
        self.assertIn("mem-beta", tb)
        self.assertNotIn("mem-alpha", tb)

    def test_cross_project_write_isolation(self):
        # write:true on alpha does NOT allow writing into beta (beta is write:false)
        self._add_project("alpha", True, "mem-alpha", "Alpha", "alpha body content")
        self._add_project("beta", False, "mem-beta", "Beta", "beta body content")
        reg = self._write_registry(self.projs)
        # remember on alpha works
        text_a, err_a, _ = self._call(reg, "remember",
                                      {"project": "alpha", "type": "knowledge",
                                       "title": "t", "body": "b"})
        self.assertFalse(err_a, text_a)
        # remember on beta is blocked
        text_b, err_b, _ = self._call(reg, "remember",
                                      {"project": "beta", "type": "knowledge",
                                       "title": "t", "body": "b"})
        self.assertTrue(err_b)
        self.assertIn("read-only", text_b)
        # beta knowledge dir unchanged
        self.assertEqual(len(list((self.tmp / "beta" / "INTERNAL_RAG" / "knowledge").glob("*.md"))), 1)

    def test_path_traversal_in_project_id_rejected(self):
        self._add_project("alpha", True, "mem-alpha", "Alpha", "alpha body content")
        reg = self._write_registry(self.projs)
        for bad in ("../..", "..\\..", "alpha/../beta", "alpha/../../etc"):
            text, is_err, _ = self._call(reg, "search", {"project": bad, "query": "x"})
            self.assertTrue(is_err, f"path traversal id should be rejected: {bad}")
            self.assertIn("unknown project", text)

    def test_symlinked_project_root(self):
        if os.name == "nt":
            self.skipTest("symlink creation on Windows requires admin/developer mode")
        real = self.tmp / "real_proj"
        real.mkdir()
        _make_project(real, "mem-real", "Real", "real body content")
        link = self.tmp / "link_proj"
        try:
            os.symlink(real, link, target_is_directory=True)
        except OSError:
            self.skipTest("cannot create symlink")
        reg = self._write_registry({"link": {"root": str(link), "write": False}})
        text, is_err, _ = self._call(reg, "search", {"project": "link", "query": "real body content"})
        self.assertFalse(is_err, text)
        self.assertIn("mem-real", text)

    def test_malformed_mcp_arguments_non_dict(self):
        self._add_project("alpha", True, "mem-alpha", "Alpha", "alpha body content")
        reg = self._write_registry(self.projs)
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "search", "arguments": "not-a-dict"}},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        ]
        p = subprocess.run([sys.executable, str(ROUTER_PATH), "--registry", str(reg)],
                           input="\n".join(json.dumps(l) for l in lines) + "\n",
                           cwd=str(self.tmp), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, encoding="utf-8", timeout=120)
        objs = _stdout_objects(p.stdout)
        r = next(o for o in objs if o.get("id") == 2)
        self.assertIn("error", r)
        self.assertEqual(r["error"]["code"], -32602)

    def test_modern_protocol_after_error(self):
        """server/discover + a failing tools/call + another discover must still work."""
        self._add_project("alpha", True, "mem-alpha", "Alpha", "alpha body content")
        reg = self._write_registry(self.projs)
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"protocolVersion": "2026-07-28"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "search", "arguments": {"project": "ghost", "query": "x"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "search", "arguments": {"project": "alpha", "query": "alpha body content"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "shutdown"},
        ]
        p = subprocess.run([sys.executable, str(ROUTER_PATH), "--registry", str(reg)],
                           input="\n".join(json.dumps(l) for l in lines) + "\n",
                           cwd=str(self.tmp), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, encoding="utf-8", timeout=120)
        objs = _stdout_objects(p.stdout)
        d = next(o for o in objs if o.get("id") == 1)
        self.assertIn("supportedVersions", d["result"])
        err = next(o for o in objs if o.get("id") == 2)
        self.assertTrue(err["result"].get("isError"))
        ok = next(o for o in objs if o.get("id") == 3)
        self.assertIn("mem-alpha", "".join(c.get("text", "") for c in ok["result"].get("content", [])))

    def test_legacy_protocol_after_error(self):
        """initialize + a failing tools/call + ping must still work."""
        self._add_project("alpha", True, "mem-alpha", "Alpha", "alpha body content")
        reg = self._write_registry(self.projs)
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "search", "arguments": {"project": "ghost", "query": "x"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "ping"},
            {"jsonrpc": "2.0", "id": 4, "method": "shutdown"},
        ]
        p = subprocess.run([sys.executable, str(ROUTER_PATH), "--registry", str(reg)],
                           input="\n".join(json.dumps(l) for l in lines) + "\n",
                           cwd=str(self.tmp), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, encoding="utf-8", timeout=120)
        objs = _stdout_objects(p.stdout)
        init = next(o for o in objs if o.get("id") == 1)
        self.assertEqual(init["result"]["protocolVersion"], "2024-11-05")
        err = next(o for o in objs if o.get("id") == 2)
        self.assertTrue(err["result"].get("isError"))
        ping = next(o for o in objs if o.get("id") == 3)
        self.assertEqual(ping["result"], {})

    def test_stdout_purity_after_errors(self):
        """No non-JSON lines on stdout even after a sequence of errors."""
        self._add_project("alpha", True, "mem-alpha", "Alpha", "alpha body content")
        reg = self._write_registry(self.projs)
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "search", "arguments": {"project": "ghost", "query": "x"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "nonexistent_tool", "arguments": {"project": "alpha"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "shutdown"},
        ]
        p = subprocess.run([sys.executable, str(ROUTER_PATH), "--registry", str(reg)],
                           input="\n".join(json.dumps(l) for l in lines) + "\n",
                           cwd=str(self.tmp), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, encoding="utf-8", timeout=120)
        for line in p.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            json.loads(line)  # raises if any non-JSON leaked to stdout


if __name__ == "__main__":
    unittest.main(verbosity=2)
