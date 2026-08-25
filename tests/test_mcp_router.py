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
            root = Path(td) / "proj"
            root.mkdir()
            reg = Path(td) / "reg.json"
            reg.write_text(json.dumps({"projects": {"p1": {"root": "proj"}}}), encoding="utf-8")
            data = router.load_registry(reg)
            self.assertEqual(data["p1"]["root"], str(root))

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
        self.assertEqual(init["result"]["serverInfo"]["name"], "internal-rag-router")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
