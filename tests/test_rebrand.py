#!/usr/bin/env python3
"""Rebrand consistency tests (v1.7.0).

Validates that the rebrand from `internal-rag` to `MCP Light Memory` is
consistent across code, docs, and examples, and that legacy aliases still work.

Zero external dependencies. Python 3.8+ stdlib only.
"""
from __future__ import annotations
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
SKILL_DIR = PROJECT_ROOT / ".agents" / "skills" / "internal-rag"
IRAG_PATH = SKILL_DIR / "irag.py"
MLM_PATH = SKILL_DIR / "mlm.py"
ROUTER_PATH = SKILL_DIR / "irag_mcp_router.py"
EXAMPLES = PROJECT_ROOT / "examples"
DOCS = PROJECT_ROOT / "docs"


def _load_irag():
    spec = importlib.util.spec_from_file_location("irag_rebrand", str(IRAG_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


class TestRebrandVersion(unittest.TestCase):
    def test_version_is_1_7_0(self):
        irag = _load_irag()
        self.assertEqual(irag.VERSION, "1.7.0")
        self.assertEqual(irag.PRODUCT_NAME, "MCP Light Memory")
        self.assertEqual(irag.PRODUCT_SLUG, "mcp-light-memory")
        self.assertEqual(irag.LEGACY_NAME, "internal-rag")

    def test_version_file_matches(self):
        v = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(v, "1.7.0")


class TestMlmShim(unittest.TestCase):
    def test_mlm_py_exists(self):
        self.assertTrue(MLM_PATH.exists(), "mlm.py shim missing")

    def test_mlm_help_shows_new_brand(self):
        p = subprocess.run([sys.executable, str(MLM_PATH), "--help"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, encoding="utf-8", timeout=60)
        self.assertEqual(p.returncode, 0)
        self.assertIn("MCP Light Memory", p.stdout)
        self.assertIn("formerly internal-rag", p.stdout)

    def test_mlm_version_matches_irag(self):
        p_mlm = subprocess.run([sys.executable, str(MLM_PATH), "--version"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", timeout=60)
        p_irag = subprocess.run([sys.executable, str(IRAG_PATH), "--version"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", timeout=60)
        self.assertEqual(p_mlm.stdout.strip(), p_irag.stdout.strip())
        self.assertIn("1.7.0", p_mlm.stdout)


class TestMcpServerName(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="irag-rebrand-mcp-"))
        rag = self.tmp / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures",
                  "hypotheses", "sessions", "sessions/.snapshots", "archive"):
            (rag / d).mkdir(parents=True, exist_ok=True)
        (rag / "WORKING_STATE.md").write_text("# Working state\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_server_info_name_is_mcp_light_memory(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        stdout = _run_stdio([sys.executable, str(IRAG_PATH), "mcp"], lines, self.tmp)
        objs = _objs(stdout)
        init = next(o for o in objs if o.get("id") == 1)
        self.assertEqual(init["result"]["serverInfo"]["name"], "mcp-light-memory")
        self.assertEqual(init["result"]["serverInfo"]["version"], "1.7.0")

    def test_server_discover_name_is_mcp_light_memory(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover",
             "params": {"protocolVersion": "2026-07-28"}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        stdout = _run_stdio([sys.executable, str(IRAG_PATH), "mcp"], lines, self.tmp)
        objs = _objs(stdout)
        d = next(o for o in objs if o.get("id") == 1)
        self.assertEqual(d["result"]["serverInfo"]["name"], "mcp-light-memory")


class TestRouterServerName(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="irag-rebrand-router-"))
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

    def test_router_server_info_name(self):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
        ]
        stdout = _run_stdio([sys.executable, str(ROUTER_PATH), "--registry", str(self.reg)],
                            lines, self.tmp)
        objs = _objs(stdout)
        init = next(o for o in objs if o.get("id") == 1)
        self.assertEqual(init["result"]["serverInfo"]["name"], "mcp-light-memory-router")
        self.assertEqual(init["result"]["serverInfo"]["version"], "1.7.0")


class TestExamplesUseNewNames(unittest.TestCase):
    def test_example_server_keys_are_mcp_light_memory(self):
        for p in EXAMPLES.glob("*.json"):
            data = json.loads(p.read_text(encoding="utf-8"))
            # find the mcpServers / mcp.servers block
            servers = data.get("mcpServers") or data.get("mcp", {}).get("servers", {})
            for key in servers:
                self.assertTrue(key.startswith("mcp-light-memory"),
                                f"{p.name}: server key '{key}' should start with 'mcp-light-memory'")

    def test_jsonc_example_server_key(self):
        for p in EXAMPLES.glob("*.jsonc"):
            text = p.read_text(encoding="utf-8")
            # strip // line comments (naive — example files have no // in strings)
            cleaned_lines = []
            for line in text.splitlines():
                stripped = line.lstrip()
                if stripped.startswith("//"):
                    continue
                # remove inline // comment
                in_str = False
                quote = ""
                cut = None
                i = 0
                while i < len(line):
                    ch = line[i]
                    if in_str:
                        if ch == "\\":
                            i += 2
                            continue
                        if ch == quote:
                            in_str = False
                    else:
                        if ch in ('"', "'"):
                            in_str = True
                            quote = ch
                        elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                            cut = i
                            break
                    i += 1
                if cut is not None:
                    line = line[:cut]
                cleaned_lines.append(line)
            cleaned = "\n".join(cleaned_lines)
            data = json.loads(cleaned)
            servers = data.get("mcpServers") or data.get("mcp", {}).get("servers", {})
            for key in servers:
                self.assertTrue(key.startswith("mcp-light-memory"),
                                f"{p.name}: server key '{key}' should start with 'mcp-light-memory'")

    def test_router_examples_exist(self):
        for name in ("warp-router.example.json",
                     "opencode-v2-router.example.jsonc",
                     "jetbrains-router.example.json"):
            self.assertTrue((EXAMPLES / name).exists(),
                            f"missing router example: {name}")


class TestDocsReferenceNewBrand(unittest.TestCase):
    def test_readme_mentions_mcp_light_memory(self):
        text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("MCP Light Memory", text)
        self.assertIn("mcp-light-memory", text)
        self.assertIn("formerly", text)

    def test_migration_doc_exists(self):
        self.assertTrue((DOCS / "MIGRATION-TO-MCP-LIGHT-MEMORY.md").exists())

    def test_branding_doc_exists(self):
        self.assertTrue((DOCS / "BRANDING.md").exists())

    def test_github_rebrand_checklist_exists(self):
        self.assertTrue((DOCS / "GITHUB-REBRAND-CHECKLIST.md").exists())

    def test_logo_assets_exist(self):
        self.assertTrue((DOCS / "assets" / "logo.svg").exists())
        self.assertTrue((DOCS / "assets" / "icon.svg").exists())


class TestLegacyAliasStillWorks(unittest.TestCase):
    def test_irag_py_help_still_works(self):
        p = subprocess.run([sys.executable, str(IRAG_PATH), "--help"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, encoding="utf-8", timeout=60)
        self.assertEqual(p.returncode, 0)

    def test_irag_py_version_still_works(self):
        p = subprocess.run([sys.executable, str(IRAG_PATH), "--version"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, encoding="utf-8", timeout=60)
        self.assertEqual(p.returncode, 0)
        self.assertIn("1.7.0", p.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)