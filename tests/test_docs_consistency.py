#!/usr/bin/env python3
"""Documentation consistency tests (P0 hardening).

Validates that documentation does not drift from the code:
  - documented project version matches the canonical VERSION constant
  - MCP protocol version sets in docs do not omit versions supported by code
    (canonical source: irag_mcp_protocol.py::SUPPORTED_VERSIONS)
  - all JSON examples in docs/ and examples/ parse
  - JSONC examples (opencode-v2) are syntactically valid after stripping comments
  - example filenames referenced by documentation exist

Zero external dependencies. Python 3.8+ stdlib only.
"""
from __future__ import annotations
import importlib.util
import json
import re
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
DOCS = PROJECT_ROOT / "docs"
EXAMPLES = PROJECT_ROOT / "examples"
SKILL_DIR = PROJECT_ROOT / ".agents" / "skills" / "internal-rag"

# Canonical version constant
VERSION_PATH = PROJECT_ROOT / "VERSION"
IRAG_PATH = SKILL_DIR / "irag.py"
PROTO_PATH = SKILL_DIR / "irag_mcp_protocol.py"


def _load_irag_version() -> str:
    return VERSION_PATH.read_text(encoding="utf-8").strip()


def _load_supported_versions() -> List[str]:
    spec = importlib.util.spec_from_file_location("proto_docconsist", str(PROTO_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(getattr(mod, "SUPPORTED_VERSIONS", []))


def _load_irag_module_version() -> str:
    spec = importlib.util.spec_from_file_location("irag_docconsist", str(IRAG_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return str(getattr(mod, "VERSION", ""))


def _strip_jsonc(text: str) -> str:
    """Strip // line comments and /* */ block comments from a JSONC string.
    Naive w.r.t. strings containing // — sufficient for our example files,
    which do not contain such edge cases. Validated by parsing afterwards."""
    out_lines: List[str] = []
    in_block = False
    for line in text.splitlines():
        if in_block:
            idx = line.find("*/")
            if idx < 0:
                continue
            line = line[idx + 2:]
            in_block = False
        # remove block comment starts on this line
        while "/*" in line:
            start = line.find("/*")
            end = line.find("*/", start + 2)
            if end < 0:
                line = line[:start]
                in_block = True
                break
            line = line[:start] + line[end + 2:]
        # strip // line comment (naive — example files have no // in strings)
        # To be safer, only strip // that appear after a position that is not
        # inside an obvious string literal. We do a simple scan.
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
        out_lines.append(line)
    return "\n".join(out_lines)


def _extract_json_blocks(text: str) -> List[str]:
    """Extract top-level ```json ... ``` fenced blocks from a Markdown text.
    Only blocks whose opening fence is exactly ```json (not ```jsonc or other)
    are extracted, and only blocks whose content looks like a JSON object/array
    (starts with '{' or '[' after stripping) are returned."""
    blocks: List[str] = []
    in_fence = False
    lang = ""
    buf: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_fence:
                content = "\n".join(buf).strip()
                if lang == "json" and content and content[0] in "{[":
                    blocks.append(content)
                buf = []
                in_fence = False
                lang = ""
            else:
                in_fence = True
                lang = stripped[3:].strip()
            continue
        if in_fence:
            buf.append(line)
    return blocks


def _extract_jsonc_blocks(text: str) -> List[str]:
    """Extract ```jsonc fenced blocks."""
    blocks: List[str] = []
    in_fence = False
    buf: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_fence:
                blocks.append("\n".join(buf))
                buf = []
                in_fence = False
            else:
                in_fence = stripped[3:].strip().startswith("jsonc")
            continue
        if in_fence:
            buf.append(line)
    if buf:
        blocks.append("\n".join(buf))
    return blocks


class TestDocsConsistency(unittest.TestCase):

    def test_canonical_version_matches_irag_module(self):
        v_file = _load_irag_version()
        v_mod = _load_irag_module_version()
        self.assertEqual(v_file, v_mod,
                         f"VERSION file={v_file!r} != irag.py VERSION={v_mod!r}")

    def test_readme_version_badge_matches_canonical(self):
        v = _load_irag_version()
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        # badge: version-1.6.0-blue
        m = re.search(r"badge/version-([0-9]+\.[0-9]+\.[0-9]+)-", readme)
        self.assertIsNotNone(m, "README version badge not found")
        self.assertEqual(m.group(1), v,
                         f"README badge version {m.group(1)} != canonical {v}")
        # "**Version:** 1.6.0"
        m2 = re.search(r"\*\*Version:\*\*\s*([0-9]+\.[0-9]+\.[0-9]+)", readme)
        self.assertIsNotNone(m2, "README Version: line not found")
        self.assertEqual(m2.group(1), v,
                         f"README Version: {m2.group(1)} != canonical {v}")

    def test_docs_protocol_versions_include_all_supported(self):
        supported = set(_load_supported_versions())
        # Gather every protocol-version token mentioned across docs.
        docs_text = ""
        for p in DOCS.glob("*.md"):
            docs_text += "\n" + p.read_text(encoding="utf-8", errors="replace")
        # Find all quoted protocol version tokens in docs.
        mentioned = set(re.findall(r"`(20\d{2}-\d{2}-\d{2})`", docs_text))
        # Every supported version must be mentioned somewhere in docs.
        missing = supported - mentioned
        self.assertFalse(missing,
                         f"Supported protocol versions not mentioned in docs: {missing}")

    def test_mcp_docs_listed_versions_are_subset_of_supported(self):
        supported = set(_load_supported_versions())
        mcp = (DOCS / "MCP.md").read_text(encoding="utf-8", errors="replace")
        # The "Legacy (...)" line lists the four legacy versions.
        m = re.search(r"\*\*Legacy\*\*\s*\(([^)]+)\)", mcp)
        self.assertIsNotNone(m, "MCP.md Legacy versions list not found")
        listed = set(re.findall(r"`(20\d{2}-\d{2}-\d{2})`", m.group(1)))
        self.assertTrue(listed.issubset(supported),
                        f"MCP.md Legacy lists unknown versions: {listed - supported}")

    def test_all_doc_json_blocks_parse(self):
        for p in DOCS.glob("*.md"):
            text = p.read_text(encoding="utf-8", errors="replace")
            for i, block in enumerate(_extract_json_blocks(text)):
                # Doc JSON blocks may contain inline comments for brevity
                # (e.g. `/* same items as plain --json */`). Strip them with
                # the JSONC stripper before parsing.
                stripped = _strip_jsonc(block)
                try:
                    json.loads(stripped)
                except Exception as e:
                    self.fail(f"{p.name} json block #{i} failed to parse: {e}\n---\n{block}\n---")

    def test_all_example_json_files_parse(self):
        for p in EXAMPLES.glob("*.json"):
            try:
                json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                self.fail(f"{p.name} failed to parse: {e}")

    def test_jsonc_example_validates(self):
        for p in EXAMPLES.glob("*.jsonc"):
            text = p.read_text(encoding="utf-8")
            stripped = _strip_jsonc(text)
            try:
                json.loads(stripped)
            except Exception as e:
                self.fail(f"{p.name} JSONC failed to validate: {e}")

    def test_doc_referenced_example_files_exist(self):
        referenced: List[str] = []
        for p in DOCS.glob("*.md"):
            text = p.read_text(encoding="utf-8", errors="replace")
            referenced += re.findall(r"`(examples/[A-Za-z0-9._-]+\.(?:json|jsonc))`", text)
        self.assertTrue(referenced, "no example files referenced in docs")
        for rel in referenced:
            full = PROJECT_ROOT / rel
            self.assertTrue(full.exists(), f"doc-referenced example missing: {rel}")

    def test_router_protocol_versions_match_canonical(self):
        # irag_mcp_router.py duplicates SUPPORTED_VERSIONS — it must match the
        # canonical constant in irag_mcp_protocol.py.
        canonical = _load_supported_versions()
        router_path = SKILL_DIR / "irag_mcp_router.py"
        text = router_path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"SUPPORTED_VERSIONS\s*=\s*\[([^\]]*)\]", text)
        self.assertIsNotNone(m, "router SUPPORTED_VERSIONS literal not found")
        router_versions = re.findall(r'"(20\d{2}-\d{2}-\d{2})"', m.group(1))
        self.assertEqual(set(router_versions), set(canonical),
                         f"router versions {router_versions} != canonical {canonical}")

    def test_examples_contain_expected_clients(self):
        names = {p.name for p in EXAMPLES.iterdir() if p.is_file()}
        for expected in ("warp.example.json", "opencode-v2.example.jsonc",
                         "opencode-legacy.example.json", "jetbrains.example.json",
                         "projects.example.json"):
            self.assertIn(expected, names, f"missing example file: {expected}")

    def test_example_files_use_python_or_python3(self):
        for p in EXAMPLES.glob("*.json"):
            text = p.read_text(encoding="utf-8")
            # Every MCP server example should reference a python executable.
            if "mcp" in text or "irag" in text:
                self.assertIn("python", text.lower(),
                              f"{p.name} MCP example does not reference python")


if __name__ == "__main__":
    unittest.main(verbosity=2)