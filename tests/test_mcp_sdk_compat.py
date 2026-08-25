#!/usr/bin/env python3
"""MCP official-SDK compatibility (optional).

Drives `irag.py mcp` and `irag_mcp_router.py` with the official `mcp` client
library (pip `mcp`). Skipped when `mcp` is not installed — the core CLI and
stdio server have ZERO required dependencies; this only proves interoperability
with a real MCP client.

CI runs this in a dedicated venv with `mcp>=2,<3`.
"""
from __future__ import annotations
import asyncio
import importlib.util
import json
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

# Skip the whole module when the optional `mcp` client is unavailable.
try:
    import mcp  # noqa: F401
    _HAS_MCP = True
except Exception:  # pragma: no cover
    _HAS_MCP = False


@unittest.skipUnless(_HAS_MCP, "optional 'mcp' SDK client not installed")
class TestMcpSdkServer(unittest.TestCase):
    def _proj(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="irag-sdk-"))
        rag = tmp / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures", "hypotheses",
                  "sessions/.snapshots", "archive"):
            (rag / d).mkdir(parents=True, exist_ok=True)
        (rag / "WORKING_STATE.md").write_text("# Working state\n", encoding="utf-8")
        text = ("---\nid: mem-sdk\ntype: knowledge\nstatus: active\ncreated: 2024-01-01\n"
                "scope: []\ntags: []\n---\n\n# SDK\n\n## Knowledge\n\n"
                "The redis cache uses LRU eviction.\n\n## Consequence\n\nNone.\n")
        (rag / "knowledge" / "sdk.md").write_text(text, encoding="utf-8")
        return tmp

    def test_single_project_server(self):
        tmp = self._proj()
        try:
            async def run():
                from mcp import ClientSession
                from mcp.client.stdio import stdio_client, StdioServerParameters
                params = StdioServerParameters(command=sys.executable, args=[str(IRAG_PATH), "mcp"],
                                                cwd=tmp)
                async with stdio_client(params) as (r, w):
                    async with ClientSession(r, w) as s:
                        init = await s.initialize()
                        self.assertIn(init.server_info.name, ("mcp-light-memory",))
                        tools = await s.list_tools()
                        names = sorted(t.name for t in tools.tools)
                        self.assertIn("search", names)
                        self.assertIn("context", names)
                        res = await s.call_tool("search", {"query": "redis cache"})
                        self.assertFalse(res.is_error)
                        blob = "".join(c.text for c in res.content)
                        self.assertIn("mem-sdk", blob)
            asyncio.run(run())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_router_server_and_projects_tool(self):
        tmp = self._proj()
        try:
            reg = tmp / "reg.json"
            reg.write_text(json.dumps({"projects": {"demo": {"root": str(tmp), "write": False}}}),
                           encoding="utf-8")

            async def run():
                from mcp import ClientSession
                from mcp.client.stdio import stdio_client, StdioServerParameters
                params = StdioServerParameters(
                    command=sys.executable, args=[str(ROUTER_PATH), "--registry", str(reg)],
                    cwd=tmp)
                async with stdio_client(params) as (r, w):
                    async with ClientSession(r, w) as s:
                        init = await s.initialize()
                        self.assertEqual(init.server_info.name, "internal-rag-router")
                        tools = await s.list_tools()
                        names = sorted(t.name for t in tools.tools)
                        self.assertIn("projects", names)
                        self.assertIn("search", names)
                        res = await s.call_tool("projects", {})
                        self.assertFalse(res.is_error)
                        data = json.loads("".join(c.text for c in res.content))
                        self.assertEqual(data["projects"][0]["id"], "demo")
            asyncio.run(run())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
