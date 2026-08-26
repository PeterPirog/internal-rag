#!/usr/bin/env python3
"""CEL L — MCP 2026-07-28 + dual-era protocol tests.

Covers:
  - server/discover (no initialize required)
  - modern tools/list (resultType, deterministic order, annotations)
  - modern tools/call (resultType, structuredContent, outputSchema)
  - invalid/unsupported modern protocol version -> error
  - legacy initialize regression (backward compat)
  - no stdout contamination
  - router modern protocol + structuredContent passthrough
  - registry strict write boolean
  - at/explain through MCP

Both A (legacy compat) and B (native 2026-07-28) lifecycle paths are tested
with RAW stdio JSON-RPC (not the SDK ClientSession.initialize, which is a
legacy-era call).
"""
from __future__ import annotations
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
SKILL_DIR = PROJECT_ROOT / ".agents" / "skills" / "internal-rag"
IRAG_PATH = SKILL_DIR / "irag.py"
ROUTER_PATH = SKILL_DIR / "irag_mcp_router.py"
PROTO_PATH = SKILL_DIR / "irag_mcp_protocol.py"

_spec = importlib.util.spec_from_file_location("proto_mod", str(PROTO_PATH))
proto = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proto)


def _run_stdio(server_args: List[str], lines: List[Dict[str, Any]], cwd: Path) -> Tuple[str, str]:
    stdin_data = "\n".join(json.dumps(l, ensure_ascii=False) for l in lines) + "\n"
    p = subprocess.run(server_args, input=stdin_data, cwd=str(cwd),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, encoding="utf-8", timeout=120)
    return p.stdout, p.stderr


def _objs(stdout: str) -> List[Dict[str, Any]]:
    out = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _find(objs: List[Dict[str, Any]], idv: Any) -> Dict[str, Any]:
    return next(o for o in objs if o.get("id") == idv)


def _make_proj(tmp: Path, mem_id: str = "mem-mcp-modern", body: str = "redis cache eviction lru") -> Path:
    rag = tmp / "INTERNAL_RAG"
    for d in ("decisions", "knowledge", "gotchas", "failures", "hypotheses",
              "sessions/.snapshots", "archive"):
        (rag / d).mkdir(parents=True, exist_ok=True)
    (rag / "WORKING_STATE.md").write_text("# Working state\n", encoding="utf-8")
    text = (f"---\nid: {mem_id}\ntype: knowledge\nstatus: active\ncreated: 2024-01-01\n"
            "scope: []\ntags: [redis, cache]\nsources: [src/cache/redis.py]\nlinks: []\n---\n\n"
            f"# {mem_id}\n\n## Knowledge\n\n{body}\n\n## Consequence\n\nNone.\n")
    (rag / "knowledge" / f"{mem_id}.md").write_text(text, encoding="utf-8")
    return tmp


class ModernMcpBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="irag-mcp-modern-"))
        _make_proj(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestServerDiscover(ModernMcpBase):
    def test_discover_without_initialize(self):
        """2026-07-28: server/discover works without a prior initialize."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                                  "io.modelcontextprotocol/clientCapabilities": {}}}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        stdout, _ = _run_stdio([sys.executable, str(IRAG_PATH), "mcp"], lines, self.tmp)
        objs = _objs(stdout)
        d = _find(objs, 1)
        res = d["result"]
        self.assertIn("2026-07-28", res["supportedVersions"])
        self.assertEqual(res["_meta"]["io.modelcontextprotocol/serverInfo"]["name"], "mcp-light-memory")
        self.assertIn("ttlMs", res)  # top-level per 2026-07-28
        self.assertIn("cacheScope", res)  # top-level per 2026-07-28
        self.assertEqual(res["resultType"], "complete")

    def test_discover_then_tools_list_modern(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                                  "io.modelcontextprotocol/clientCapabilities": {}}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list",
             "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                                  "io.modelcontextprotocol/clientCapabilities": {}}}},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        ]
        stdout, _ = _run_stdio([sys.executable, str(IRAG_PATH), "mcp"], lines, self.tmp)
        objs = _objs(stdout)
        tl = _find(objs, 2)["result"]
        self.assertEqual(tl.get("resultType"), "complete")
        names = [t["name"] for t in tl["tools"]]
        self.assertEqual(names, sorted(names))  # deterministic order
        self.assertIn("ttlMs", tl)  # top-level per 2026-07-28
        self.assertIn("cacheScope", tl)  # top-level per 2026-07-28

    def test_unsupported_version_errors(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2099-01-01"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        stdout, _ = _run_stdio([sys.executable, str(IRAG_PATH), "mcp"], lines, self.tmp)
        objs = _objs(stdout)
        d = _find(objs, 1)
        self.assertIn("error", d)
        self.assertEqual(d["error"]["code"], -32022)  # UnsupportedProtocolVersionError
        self.assertIn("Unsupported", d["error"]["message"])


class TestModernToolsCall(ModernMcpBase):
    def test_search_structured_content_and_schema(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"protocolVersion": "2026-07-28",
                        "clientCapabilities": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "search", "arguments": {"query": "redis cache"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        ]
        stdout, _ = _run_stdio([sys.executable, str(IRAG_PATH), "mcp"], lines, self.tmp)
        objs = _objs(stdout)
        r = _find(objs, 2)["result"]
        self.assertEqual(r.get("resultType"), "complete")
        self.assertIn("structuredContent", r)
        sc = r["structuredContent"]
        self.assertIn("abstained", sc)
        self.assertIn("confidence_kind", sc)
        self.assertEqual(sc["confidence_kind"], "heuristic")
        self.assertNotIn("outputSchema", r)
        self.assertIn("results", sc)

    def test_search_at_and_explain(self):
        """CEL D: MCP search accepts at + explain."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "search",
                        "arguments": {"query": "redis", "at": "2024-06-01", "explain": True}}},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        ]
        stdout, _ = _run_stdio([sys.executable, str(IRAG_PATH), "mcp"], lines, self.tmp)
        objs = _objs(stdout)
        r = _find(objs, 2)["result"]
        sc = r.get("structuredContent", {})
        self.assertIn("results", sc)

    def test_guard_structured(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"protocolVersion": "2026-07-28",
                        "clientCapabilities": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "guard", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        ]
        stdout, _ = _run_stdio([sys.executable, str(IRAG_PATH), "mcp"], lines, self.tmp)
        objs = _objs(stdout)
        r = _find(objs, 2)["result"]
        self.assertIn("structuredContent", r)
        self.assertIn("ok", r["structuredContent"])

    def test_status_and_tasks_structured(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"protocolVersion": "2026-07-28",
                        "clientCapabilities": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "status", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "tasks", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "shutdown"},
        ]
        stdout, _ = _run_stdio([sys.executable, str(IRAG_PATH), "mcp"], lines, self.tmp)
        objs = _objs(stdout)
        for rid in (2, 3):
            r = _find(objs, rid)["result"]
            self.assertIn("structuredContent", r)
            self.assertNotIn("outputSchema", r)


class TestLegacyRegression(ModernMcpBase):
    def test_legacy_initialize_still_works(self):
        """A: legacy compatibility — initialize/tools/list/tools/call unchanged."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "t", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "search", "arguments": {"query": "redis"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "ping"},
            {"jsonrpc": "2.0", "id": 5, "method": "shutdown"},
        ]
        stdout, _ = _run_stdio([sys.executable, str(IRAG_PATH), "mcp"], lines, self.tmp)
        objs = _objs(stdout)
        init = _find(objs, 1)
        self.assertEqual(init["result"]["protocolVersion"], "2024-11-05")
        tools = _find(objs, 2)
        self.assertIn("search", [t["name"] for t in tools["result"]["tools"]])
        call = _find(objs, 3)
        self.assertFalse(call["result"]["isError"])
        # legacy clients still get content text
        self.assertTrue(call["result"]["content"][0]["text"])

    def test_no_stdout_contamination(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"protocolVersion": "2026-07-28"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "search", "arguments": {"query": "x"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        ]
        stdout, _ = _run_stdio([sys.executable, str(IRAG_PATH), "mcp"], lines, self.tmp)
        for line in stdout.splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)  # every stdout line must be valid JSON-RPC
            self.assertIn("jsonrpc", obj)


class TestProtocolHelpers(unittest.TestCase):
    def test_negotiate_known_legacy(self):
        self.assertEqual(proto.negotiate_version("2024-11-05"), "2024-11-05")
        self.assertEqual(proto.negotiate_version("2025-06-18"), "2025-06-18")

    def test_negotiate_modern_counters_to_legacy(self):
        # 2026-07-28 is NOT negotiable via the legacy initialize handshake —
        # a modern revision is countered to the latest supported legacy version.
        self.assertEqual(proto.negotiate_version("2026-07-28"), proto.DEFAULT_LEGACY)

    def test_negotiate_unknown_falls_back(self):
        self.assertEqual(proto.negotiate_version("2099-01-01"), proto.DEFAULT_LEGACY)

    def test_discover_result_shape(self):
        r = proto.discover_result("x", "1.0", "instr")
        self.assertIn("2026-07-28", r["supportedVersions"])
        self.assertEqual(r["_meta"]["io.modelcontextprotocol/serverInfo"]["name"], "x")
        self.assertIn("ttlMs", r)

    def test_tool_call_result_modern_fields(self):
        r = proto.tool_call_result("txt", False, {"k": 1})
        self.assertEqual(r["resultType"], "complete")
        self.assertIn("structuredContent", r)
        self.assertNotIn("outputSchema", r)


class TestRouterModern(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="irag-router-modern-"))
        proj = self.tmp / "proj"
        _make_proj(proj)
        self.reg = self.tmp / "reg.json"
        self.reg.write_text(json.dumps({"projects": {"demo": {"root": str(proj), "write": False}}}),
                            encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_router_discover(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"protocolVersion": "2026-07-28"}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        stdout, _ = _run_stdio([sys.executable, str(ROUTER_PATH), "--registry", str(self.reg)],
                               lines, self.tmp)
        objs = _objs(stdout)
        d = _find(objs, 1)
        self.assertEqual(d["result"]["_meta"]["io.modelcontextprotocol/serverInfo"]["name"], "mcp-light-memory-router")
        self.assertIn("2026-07-28", d["result"]["supportedVersions"])

    def test_router_projects_structured(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"protocolVersion": "2026-07-28"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "projects", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        ]
        stdout, _ = _run_stdio([sys.executable, str(ROUTER_PATH), "--registry", str(self.reg)],
                               lines, self.tmp)
        objs = _objs(stdout)
        r = _find(objs, 2)["result"]
        self.assertEqual(r.get("resultType"), "complete")
        sc = r.get("structuredContent", {})
        self.assertIn("projects", sc)
        self.assertEqual(sc["projects"][0]["id"], "demo")


if __name__ == "__main__":
    unittest.main(verbosity=2)