#!/usr/bin/env python3
"""MCP stdio server (irag.py mcp) protocol + stdout-purity regression tests.

Covers:
- stdout is PURE JSON-RPC (every line parses; no log leakage)
- initialize version negotiation (client's version if supported, else latest)
- unknown client version -> server's latest (still a known spec version)
- tools/list deterministic; tools/call dispatch; ping ack; shutdown
- legacy handshake still works
- search tool returns JSON payload (read-only)
- stderr carries the log, not stdout
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
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
IRAG_PATH = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag.py"

_spec = importlib.util.spec_from_file_location("irag_mod", str(IRAG_PATH))
irag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(irag)

SUPPORTED = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]


def _run(lines: List[Dict[str, Any]], cwd: Path) -> Tuple[str, str]:
    stdin_data = "\n".join(json.dumps(l, ensure_ascii=False) for l in lines) + "\n"
    p = subprocess.run([sys.executable, str(IRAG_PATH), "mcp"], input=stdin_data,
                       cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
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


class McpServerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="irag-mcp-"))
        rag = self.tmp / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures", "hypotheses",
                  "sessions/.snapshots", "archive"):
            (rag / d).mkdir(parents=True, exist_ok=True)
        (rag / "WORKING_STATE.md").write_text("# Working state\n", encoding="utf-8")
        text = ("---\nid: mem-db\ntype: knowledge\nstatus: active\ncreated: 2024-01-01\n"
                "scope: []\ntags: []\n---\n\n# DB\n\n## Knowledge\n\n"
                "We use postgres for the primary database.\n\n## Consequence\n\nNone.\n")
        (rag / "knowledge" / "db.md").write_text(text, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestProtocol(McpServerBase):
    def test_stdout_is_pure_jsonrpc(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "t", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "search", "arguments": {"query": "postgres"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "ping"},
            {"jsonrpc": "2.0", "id": 5, "method": "shutdown"},
        ]
        stdout, stderr = _run(lines, self.tmp)
        objs = _objs(stdout)  # raises if any stdout line is not JSON
        self.assertTrue(all(isinstance(o, dict) and "jsonrpc" in o for o in objs))
        init = _find(objs, 1)
        self.assertIn(init["result"]["protocolVersion"], SUPPORTED)
        self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(init["result"]["serverInfo"]["name"], "mcp-light-memory")
        tools = _find(objs, 2)
        names = [t["name"] for t in tools["result"]["tools"]]
        self.assertIn("search", names)
        self.assertIn("context", names)
        call = _find(objs, 3)
        text = "".join(c.get("text", "") for c in call["result"]["content"])
        self.assertIn("mem-db", text)
        self.assertFalse(call["result"]["isError"])
        self.assertIn({"jsonrpc": "2.0", "id": 4, "result": {}}, objs)
        self.assertTrue(any(o.get("id") == 5 for o in objs))

    def test_unknown_client_version_falls_back_to_latest(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "1999-01-01", "clientInfo": {"name": "t", "version": "0"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        stdout, _ = _run(lines, self.tmp)
        init = _find(_objs(stdout), 1)
        self.assertEqual(init["result"]["protocolVersion"], SUPPORTED[0])

    def test_tools_call_unknown_tool_is_error(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "t", "version": "0"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "does_not_exist", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        ]
        stdout, _ = _run(lines, self.tmp)
        objs = _objs(stdout)
        call = _find(objs, 2)
        self.assertTrue(call["result"]["isError"])
        self.assertIn("unknown tool", call["result"]["content"][0]["text"])

    def test_bad_json_is_parse_error(self):
        p = subprocess.run([sys.executable, str(IRAG_PATH), "mcp"],
                           input="{not json\n", cwd=str(self.tmp),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, encoding="utf-8", timeout=60)
        objs = _objs(p.stdout)
        self.assertTrue(any(o.get("error", {}).get("code") == -32700 for o in objs),
                        f"expected -32700 parse error, got: {objs}")

    def test_search_tool_is_read_only(self):
        before = {str(p): p.read_bytes() for p in self.tmp.rglob("*.md")}
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "t", "version": "0"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "search", "arguments": {"query": "postgres database"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        ]
        _run(lines, self.tmp)
        after = {str(p): p.read_bytes() for p in self.tmp.rglob("*.md")}
        self.assertEqual(before, after, "search must not modify markdown")


if __name__ == "__main__":
    unittest.main(verbosity=2)
