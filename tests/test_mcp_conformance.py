#!/usr/bin/env python3
"""MCP 2026-07-28 conformance/golden tests.

Tests based on the final MCP specification (2026-07-28), NOT on the project's
own assumptions. Validates the wire format against the official schema:
  - https://modelcontextprotocol.io/specification/2026-07-28/basic
  - https://modelcontextprotocol.io/specification/2026-07-28/server/tools
  - https://modelcontextprotocol.io/specification/2026-07-28/server/discover

Covers:
  1. Direct modern tools/list without prior discover
  2. Direct modern tools/call without prior discover
  3. server/discover with correct _meta
  4. Per-request _meta protocolVersion
  5. serverInfo in _meta['io.modelcontextprotocol/serverInfo']
  6. ttlMs and cacheScope as top-level result fields
  7. Correct cacheScope values ('public' | 'private')
  8. resultType required on every result
  9. structuredContent as result data
  10. outputSchema in tool definitions (NOT in tool/call results)
  11. Malformed/unsupported protocol version error
  12. Legacy initialize regression
  13. stdout purity

Zero external dependencies. Python 3.8+ stdlib only.
"""
from __future__ import annotations
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
SKILL_DIR = PROJECT_ROOT / ".agents" / "skills" / "internal-rag"
IRAG_PATH = SKILL_DIR / "irag.py"
ROUTER_PATH = SKILL_DIR / "irag_mcp_router.py"
PROTO_PATH = SKILL_DIR / "irag_mcp_protocol.py"

MODERN_VERSION = "2026-07-28"
META_PV = "io.modelcontextprotocol/protocolVersion"
META_SI = "io.modelcontextprotocol/serverInfo"
META_CI = "io.modelcontextprotocol/clientInfo"
META_CC = "io.modelcontextprotocol/clientCapabilities"
ERR_UNSUP = -32022
ERR_INVALID_PARAMS = -32602


def _run_stdio(server_args: List[str], lines: List[Dict[str, Any]],
               cwd: Path) -> str:
    stdin_data = "\n".join(json.dumps(l, ensure_ascii=False) for l in lines) + "\n"
    p = subprocess.run(server_args, input=stdin_data.encode("utf-8"),
                       cwd=str(cwd), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=120)
    return p.stdout.decode("utf-8", errors="replace")


def _objs(stdout: str) -> List[Dict[str, Any]]:
    out = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _find(objs: List[Dict[str, Any]], rid: Any) -> Dict[str, Any]:
    for o in objs:
        if o.get("id") == rid:
            return o
    raise AssertionError(f"no response with id={rid}")


def _modern_meta(version: str = MODERN_VERSION) -> Dict[str, Any]:
    """Build a modern _meta block per MCP 2026-07-28.

    `cc` controls clientCapabilities: None -> key ABSENT (malformed
    modern request), any value -> key present with that value.
    """
    return {
        META_PV: version,
        META_CI: {"name": "conformance-test", "version": "1.0.0"},
        META_CC: {},
    }


def _modern_meta_missing_cc(version: str = MODERN_VERSION) -> Dict[str, Any]:
    """Modern _meta WITHOUT the required clientCapabilities key."""
    m = _modern_meta(version)
    del m[META_CC]
    return m


class ConformanceBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mcp-conf-"))
        rag = self.tmp / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures",
                  "hypotheses", "sessions", "sessions/.snapshots", "archive"):
            (rag / d).mkdir(parents=True, exist_ok=True)
        (rag / "WORKING_STATE.md").write_text("# Working state\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        stdout = _run_stdio([sys.executable, str(IRAG_PATH), "mcp"], lines, self.tmp)
        return _objs(stdout)


class TestDirectModernToolsList(ConformanceBase):
    """1. Direct modern tools/list without prior discover."""

    def test_tools_list_without_discover(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        self.assertEqual(r.get("resultType"), "complete")
        self.assertIn("tools", r)
        self.assertIsInstance(r["tools"], list)
        self.assertGreater(len(r["tools"]), 0)
        # deterministic order
        names = [t["name"] for t in r["tools"]]
        self.assertEqual(names, sorted(names))


class TestDirectModernToolsCall(ConformanceBase):
    """2. Direct modern tools/call without prior discover."""

    def test_tools_call_status_without_discover(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"_meta": _modern_meta(),
                        "name": "status", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        self.assertEqual(r.get("resultType"), "complete")
        self.assertIn("content", r)
        self.assertIn("isError", r)


class TestServerDiscover(ConformanceBase):
    """3. server/discover with correct _meta."""

    def test_discover_correct_shape(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        self.assertEqual(r.get("resultType"), "complete")
        self.assertIn("supportedVersions", r)
        self.assertIn(MODERN_VERSION, r["supportedVersions"])
        self.assertIn("capabilities", r)
        self.assertIn("instructions", r)


class TestPerRequestMeta(ConformanceBase):
    """4. Per-request _meta protocolVersion."""

    def test_two_requests_same_connection_different_versions(self):
        """A modern and a legacy request on the same connection should both work."""
        lines = [
            # Modern request (with _meta)
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta()}},
            # Legacy request (no _meta, uses initialize)
            {"jsonrpc": "2.0", "id": 2, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        ]
        objs = self._run(lines)
        # Modern tools/list
        r1 = _find(objs, 1)["result"]
        self.assertEqual(r1.get("resultType"), "complete")
        # Legacy initialize
        r2 = _find(objs, 2)["result"]
        self.assertIn("protocolVersion", r2)


class TestServerInfoNamespaced(ConformanceBase):
    """5. serverInfo in _meta['io.modelcontextprotocol/serverInfo']."""

    def test_discover_server_info_in_meta(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        self.assertIn("_meta", r)
        self.assertIn(META_SI, r["_meta"])
        si = r["_meta"][META_SI]
        self.assertEqual(si["name"], "mcp-light-memory")
        self.assertIn("version", si)

    def test_discover_no_top_level_serverInfo(self):
        """Per 2026-07-28, serverInfo is NOT a top-level field in discover."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        self.assertNotIn("serverInfo", r)  # must be in _meta, not top-level


class TestCacheFields(ConformanceBase):
    """6. ttlMs and cacheScope as top-level result fields."""

    def test_discover_has_ttlMs_and_cacheScope_top_level(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        self.assertIn("ttlMs", r)
        self.assertIn("cacheScope", r)

    def test_tools_list_has_ttlMs_and_cacheScope_top_level(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        self.assertIn("ttlMs", r)
        self.assertIn("cacheScope", r)

    def test_cacheScope_values(self):
        """7. Correct cacheScope values: 'public' or 'private'."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        ]
        objs = self._run(lines)
        for rid in (1, 2):
            r = _find(objs, rid)["result"]
            self.assertIn(r["cacheScope"], ("public", "private"),
                          f"result {rid}: invalid cacheScope={r['cacheScope']!r}")


class TestResultType(ConformanceBase):
    """8. resultType required on every result."""

    def test_discover_has_resultType(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        self.assertEqual(r.get("resultType"), "complete")

    def test_tools_list_has_resultType(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        self.assertEqual(r.get("resultType"), "complete")

    def test_tools_call_has_resultType(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"_meta": _modern_meta(),
                        "name": "status", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        self.assertEqual(r.get("resultType"), "complete")


class TestStructuredContent(ConformanceBase):
    """9. structuredContent as result data."""

    def test_search_returns_structuredContent(self):
        # Seed a memory
        mem = (f"---\nid: mem-conf-search\ntype: knowledge\nstatus: active\n"
               "created: 2024-01-01\nscope: []\ntags: [test]\nsources: []\nlinks: []\n---\n\n"
               "# Test memory\n\n## Knowledge\n\ntest search content unique\n\n## Consequence\n\nNone.\n")
        (self.tmp / "INTERNAL_RAG" / "knowledge" / "test.md").write_text(mem, encoding="utf-8")
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"_meta": _modern_meta(),
                        "name": "search",
                        "arguments": {"query": "test search content unique"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        self.assertIn("structuredContent", r)
        sc = r["structuredContent"]
        self.assertIsInstance(sc, dict)


class TestOutputSchemaPlacement(ConformanceBase):
    """10. outputSchema in tool definitions (NOT in tool/call results)."""

    def test_tools_list_contains_outputSchema(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        tools = r["tools"]
        # At least some tools should have outputSchema in their definition
        has_schema = any("outputSchema" in t for t in tools)
        self.assertTrue(has_schema, "no tool has outputSchema in its definition")

    def test_tool_call_result_has_no_outputSchema(self):
        """Per 2026-07-28, outputSchema is NOT in the tool/call result."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"_meta": _modern_meta(),
                        "name": "status", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        self.assertNotIn("outputSchema", r,
                         "outputSchema must NOT be in tool/call result per 2026-07-28")


class TestUnsupportedVersion(ConformanceBase):
    """11. Malformed/unsupported protocol version error."""

    def test_unsupported_version_returns_error_32022(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"_meta": _modern_meta("2099-01-01")}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        d = _find(objs, 1)
        self.assertIn("error", d)
        self.assertEqual(d["error"]["code"], ERR_UNSUP)
        self.assertIn("supported", d["error"].get("data", {}))
        self.assertIn("requested", d["error"].get("data", {}))


class TestUnsupportedVersionOnToolMethods(ConformanceBase):
    """11b. P4/P6: unsupported version must be rejected on tools/list and
    tools/call as well — validation applies to EVERY modern request."""

    def test_tools_list_unsupported_version_returns_error_32022(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta("2099-01-01")}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        d = _find(objs, 1)
        self.assertIn("error", d, "tools/list with unsupported version must error")
        self.assertEqual(d["error"]["code"], ERR_UNSUP)
        data = d["error"].get("data", {})
        self.assertIn("supported", data)
        self.assertIn("requested", data)
        self.assertNotIn(MODERN_VERSION, [data.get("requested")])

    def test_tools_call_unsupported_version_returns_error_32022(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"_meta": _modern_meta("2099-01-01"),
                        "name": "status", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        d = _find(objs, 1)
        self.assertIn("error", d, "tools/call with unsupported version must error")
        self.assertEqual(d["error"]["code"], ERR_UNSUP)
        self.assertIn("supported", d["error"].get("data", {}))

    def test_tools_list_valid_version_still_works_after_reject(self):
        """A rejected request must not poison the connection."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta("2099-01-01")}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        ]
        objs = self._run(lines)
        self.assertIn("error", _find(objs, 1))
        r = _find(objs, 2)["result"]
        self.assertEqual(r.get("resultType"), "complete")
        self.assertIn("tools", r)

    def test_tools_list_without_meta_is_legacy_and_works(self):
        """No _meta at all = legacy request — must NOT be rejected as modern."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        d = _find(objs, 1)
        self.assertNotIn("error", d, "legacy tools/list must not be rejected")
        self.assertIn("tools", d["result"])


class TestRouterUnsupportedVersion(unittest.TestCase):
    """11c. P6: the router must reject unsupported versions on tool methods."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mcp-conf-roun-"))
        root = self.tmp / "proj"
        rag = root / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures",
                  "hypotheses", "sessions", "sessions/.snapshots", "archive"):
            (rag / d).mkdir(parents=True, exist_ok=True)
        (rag / "WORKING_STATE.md").write_text("# ws\n", encoding="utf-8")
        self.reg = self.tmp / "reg.json"
        self.reg.write_text(json.dumps({"projects": {
            "p": {"root": str(root), "write": False}}}), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        stdout = _run_stdio([sys.executable, str(ROUTER_PATH),
                             "--registry", str(self.reg)], lines, self.tmp)
        return _objs(stdout)

    def test_router_tools_list_unsupported_version(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta("2099-01-01")}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        d = _find(self._run(lines), 1)
        self.assertIn("error", d)
        self.assertEqual(d["error"]["code"], ERR_UNSUP)
        self.assertIn("supported", d["error"].get("data", {}))

    def test_router_tools_call_unsupported_version(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"_meta": _modern_meta("2099-01-01"),
                        "name": "status", "arguments": {"project": "p"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        d = _find(self._run(lines), 1)
        self.assertIn("error", d)
        self.assertEqual(d["error"]["code"], ERR_UNSUP)


class TestEraSeparation(ConformanceBase):
    """14. Modern vs legacy era separation.

    - Modern era: 2026-07-28+, per-request _meta + server/discover.
    - Legacy era: 2024-11-05 … 2025-11-25, initialize handshake.
    - 2026-07-28 is NOT negotiable via initialize.
    - server/discover advertises ONLY modern revisions.
    - A legacy revision in per-request _meta is rejected in the modern era.
    """

    def test_discover_supported_versions_is_modern_subset(self):
        """1. server/discover supportedVersions == modern subset, no 2025-11-25."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        sv = r["supportedVersions"]
        self.assertIn(MODERN_VERSION, sv)
        self.assertNotIn("2025-11-25", sv)
        self.assertNotIn("2025-06-18", sv)
        self.assertNotIn("2025-03-26", sv)
        self.assertNotIn("2024-11-05", sv)

    def test_initialize_with_modern_version_counters_to_legacy(self):
        """2. initialize with 2026-07-28 does NOT negotiate the modern era —
        the server counters with the latest supported LEGACY revision."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": MODERN_VERSION,
                        "clientInfo": {"name": "era-test", "version": "1.0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        init = _find(objs, 1)
        self.assertIn("result", init)
        negotiated = init["result"]["protocolVersion"]
        self.assertNotEqual(negotiated, MODERN_VERSION,
                            "2026-07-28 must not be negotiated via initialize")
        self.assertEqual(negotiated, "2025-11-25",
                         "counter-offer must be the latest legacy revision")

    def test_initialize_with_legacy_2025_11_25_still_works(self):
        """3. initialize with 2025-11-25 negotiates itself (legacy era)."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-11-25",
                        "clientInfo": {"name": "era-test", "version": "1.0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        init = _find(objs, 1)
        self.assertIn("result", init)
        self.assertEqual(init["result"]["protocolVersion"], "2025-11-25")

    def test_modern_request_with_legacy_version_rejected(self):
        """4. Modern tools/list with _meta protocolVersion=2025-11-25 is
        rejected as unsupported in the modern era (not silently downgraded)."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta("2025-11-25")}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        d = _find(objs, 1)
        self.assertIn("error", d, "legacy revision in modern _meta must be rejected")
        self.assertEqual(d["error"]["code"], ERR_UNSUP)
        data = d["error"].get("data", {})
        self.assertIn("supported", data)
        self.assertNotIn("2025-11-25", data["supported"],
                         "supported list for modern era must not contain legacy revisions")

    def test_modern_tools_list_with_2026_07_28_works(self):
        """5. 2026-07-28 modern tools/list still works."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta(MODERN_VERSION)}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        self.assertEqual(r.get("resultType"), "complete")
        self.assertIn("tools", r)
        self.assertGreater(len(r["tools"]), 0)


class TestClientCapabilitiesValidation(ConformanceBase):
    """15. Required per-request clientCapabilities (MCP 2026-07-28).

    Per the official schema, EVERY modern request must carry:
      - io.modelcontextprotocol/protocolVersion (string)
      - io.modelcontextprotocol/clientCapabilities (object)
    clientInfo is optional. Missing/wrong-type clientCapabilities is
    malformed required metadata -> JSON-RPC -32602 (invalid params),
    NOT -32021 (reserved for a specific required capability).
    """

    def test_missing_clientCapabilities_returns_32602(self):
        """1. Missing clientCapabilities with a valid modern version -> -32602."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta_missing_cc()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        d = _find(objs, 1)
        self.assertIn("error", d, "missing clientCapabilities must be rejected")
        self.assertEqual(d["error"]["code"], ERR_INVALID_PARAMS)
        self.assertNotEqual(d["error"]["code"], -32021)

    def test_wrong_type_clientCapabilities_returns_32602(self):
        """2. clientCapabilities null / list / string -> -32602."""
        for bad in (None, ["x"], "tools"):
            meta = _modern_meta()
            meta[META_CC] = bad
            lines = [
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
                 "params": {"_meta": meta}},
                {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
            ]
            d = _find(self._run(lines), 1)
            self.assertIn("error", d,
                          f"clientCapabilities={bad!r} must be rejected")
            self.assertEqual(d["error"]["code"], ERR_INVALID_PARAMS,
                             f"clientCapabilities={bad!r} must be -32602")

    def test_empty_clientCapabilities_object_accepted(self):
        """3. clientCapabilities={} is a valid object -> accepted."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)
        self.assertNotIn("error", r, "clientCapabilities={} must be accepted")
        self.assertIn("tools", r["result"])

    def test_legacy_no_meta_accepted(self):
        """4. Legacy flow (no _meta at all) must NOT be rejected."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        d = _find(objs, 1)
        self.assertNotIn("error", d, "legacy request without _meta must work")
        self.assertIn("tools", d["result"])

    def test_connection_survives_malformed_request(self):
        """5. A malformed modern request must not poison the connection —
        a subsequent valid request still works."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta_missing_cc()}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        ]
        objs = self._run(lines)
        self.assertEqual(_find(objs, 1)["error"]["code"], ERR_INVALID_PARAMS)
        r = _find(objs, 2)
        self.assertNotIn("error", r)
        self.assertIn("tools", r["result"])

    def test_unsupported_version_still_32022_with_data(self):
        """Unsupported modern version keeps -32022 + supported/requested."""
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta_missing_cc("2099-01-01")}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        d = _find(self._run(lines), 1)
        self.assertEqual(d["error"]["code"], ERR_UNSUP)
        self.assertIn("supported", d["error"].get("data", {}))
        self.assertIn("requested", d["error"].get("data", {}))


class TestRouterClientCapabilitiesValidation(unittest.TestCase):
    """15b. The router enforces the SAME clientCapabilities rules."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mcp-conf-rcc-"))
        root = self.tmp / "proj"
        rag = root / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures",
                  "hypotheses", "sessions", "sessions/.snapshots", "archive"):
            (rag / d).mkdir(parents=True, exist_ok=True)
        (rag / "WORKING_STATE.md").write_text("# ws\n", encoding="utf-8")
        self.reg = self.tmp / "reg.json"
        self.reg.write_text(json.dumps({"projects": {
            "p": {"root": str(root), "write": False}}}), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        stdout = _run_stdio([sys.executable, str(ROUTER_PATH),
                             "--registry", str(self.reg)], lines, self.tmp)
        return _objs(stdout)

    def test_router_missing_clientCapabilities_returns_32602(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta_missing_cc()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        d = _find(self._run(lines), 1)
        self.assertIn("error", d)
        self.assertEqual(d["error"]["code"], ERR_INVALID_PARAMS)

    def test_router_wrong_type_clientCapabilities_returns_32602(self):
        meta = _modern_meta()
        meta[META_CC] = "not-an-object"
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": meta}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        d = _find(self._run(lines), 1)
        self.assertIn("error", d)
        self.assertEqual(d["error"]["code"], ERR_INVALID_PARAMS)

    def test_router_empty_object_accepted(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        d = _find(self._run(lines), 1)
        self.assertNotIn("error", d)
        self.assertIn("tools", d["result"])

    def test_router_legacy_no_meta_accepted(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        d = _find(self._run(lines), 1)
        self.assertNotIn("error", d)
        self.assertIn("tools", d["result"])

    def test_router_connection_survives_malformed(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta_missing_cc()}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        ]
        objs = self._run(lines)
        self.assertEqual(_find(objs, 1)["error"]["code"], ERR_INVALID_PARAMS)
        r = _find(objs, 2)
        self.assertNotIn("error", r)
        self.assertIn("tools", r["result"])


class TestRouterEraSeparation(unittest.TestCase):
    """6. The router must behave identically for era separation."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mcp-conf-rou-"))
        root = self.tmp / "proj"
        rag = root / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures",
                  "hypotheses", "sessions", "sessions/.snapshots", "archive"):
            (rag / d).mkdir(parents=True, exist_ok=True)
        (rag / "WORKING_STATE.md").write_text("# ws\n", encoding="utf-8")
        self.reg = self.tmp / "reg.json"
        self.reg.write_text(json.dumps({"projects": {
            "p": {"root": str(root), "write": False}}}), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        stdout = _run_stdio([sys.executable, str(ROUTER_PATH),
                             "--registry", str(self.reg)], lines, self.tmp)
        return _objs(stdout)

    def test_router_discover_modern_subset(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        r = _find(self._run(lines), 1)["result"]
        self.assertIn(MODERN_VERSION, r["supportedVersions"])
        self.assertNotIn("2025-11-25", r["supportedVersions"])

    def test_router_initialize_modern_counters_to_legacy(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": MODERN_VERSION}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        init = _find(self._run(lines), 1)
        self.assertNotEqual(init["result"]["protocolVersion"], MODERN_VERSION)
        self.assertEqual(init["result"]["protocolVersion"], "2025-11-25")

    def test_router_modern_request_with_legacy_version_rejected(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta("2025-11-25")}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        d = _find(self._run(lines), 1)
        self.assertIn("error", d)
        self.assertEqual(d["error"]["code"], ERR_UNSUP)
        self.assertNotIn("2025-11-25", d["error"].get("data", {}).get("supported", []))


class TestLegacyInitializeRegression(ConformanceBase):
    """12. Legacy initialize regression."""

    def test_legacy_initialize_works(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "ping"},
            {"jsonrpc": "2.0", "id": 4, "method": "shutdown"},
        ]
        objs = self._run(lines)
        init = _find(objs, 1)
        self.assertIn("protocolVersion", init["result"])
        self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
        # serverInfo at top-level for legacy (not in _meta)
        self.assertIn("serverInfo", init["result"])
        # tools/list works after initialize
        tl = _find(objs, 2)["result"]
        self.assertIn("tools", tl)
        # ping works
        ping = _find(objs, 3)
        self.assertEqual(ping["result"], {})


class TestStdoutPurity(ConformanceBase):
    """13. stdout purity — only JSON-RPC messages."""

    def test_stdout_only_json(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"_meta": _modern_meta(),
                        "name": "status", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 3, "method": "server/discover",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 4, "method": "shutdown"},
        ]
        stdout = _run_stdio([sys.executable, str(IRAG_PATH), "mcp"], lines, self.tmp)
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            json.loads(line)  # raises if any non-JSON leaked to stdout


class TestRouterConformance(unittest.TestCase):
    """Router MCP 2026-07-28 conformance."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mcp-conf-router-"))
        root = self.tmp / "proj"
        rag = root / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures",
                  "hypotheses", "sessions", "sessions/.snapshots", "archive"):
            (rag / d).mkdir(parents=True, exist_ok=True)
        (rag / "WORKING_STATE.md").write_text("# ws\n", encoding="utf-8")
        self.reg = self.tmp / "reg.json"
        self.reg.write_text(json.dumps({"projects": {
            "p": {"root": str(root), "write": False}}}), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        stdout = _run_stdio([sys.executable, str(ROUTER_PATH),
                             "--registry", str(self.reg)], lines, self.tmp)
        return _objs(stdout)

    def test_router_discover_modern(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        self.assertEqual(r.get("resultType"), "complete")
        self.assertIn(MODERN_VERSION, r["supportedVersions"])
        self.assertIn(META_SI, r["_meta"])
        self.assertEqual(r["_meta"][META_SI]["name"], "mcp-light-memory-router")

    def test_router_direct_tools_list_modern(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        objs = self._run(lines)
        r = _find(objs, 1)["result"]
        self.assertEqual(r.get("resultType"), "complete")
        self.assertIn("ttlMs", r)
        self.assertIn("cacheScope", r)

    def test_router_stdout_purity(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list",
             "params": {"_meta": _modern_meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        stdout = _run_stdio([sys.executable, str(ROUTER_PATH),
                             "--registry", str(self.reg)], lines, self.tmp)
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            json.loads(line)


if __name__ == "__main__":
    unittest.main(verbosity=2)