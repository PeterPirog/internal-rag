#!/usr/bin/env python3
"""Documentation and language consistency tests.

The suite keeps the installation/documentation contracts aligned with code and
prevents user-facing documentation, source comments, and docstrings from
silently drifting back to Polish. Zero external dependencies; Python 3.8+.
"""
from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path
from typing import List

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
DOCS = PROJECT_ROOT / "docs"
EXAMPLES = PROJECT_ROOT / "examples"
SKILL_DIR = PROJECT_ROOT / ".agents" / "skills" / "internal-rag"
VERSION_PATH = PROJECT_ROOT / "VERSION"
IRAG_PATH = SKILL_DIR / "irag.py"
PROTO_PATH = SKILL_DIR / "irag_mcp_protocol.py"


def _load_irag_version() -> str:
    return VERSION_PATH.read_text(encoding="utf-8").strip()


def _load_supported_versions() -> List[str]:
    spec = importlib.util.spec_from_file_location("proto_docconsist", str(PROTO_PATH))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return list(getattr(mod, "SUPPORTED_VERSIONS", []))


def _load_irag_module_version() -> str:
    spec = importlib.util.spec_from_file_location("irag_docconsist", str(IRAG_PATH))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return str(getattr(mod, "VERSION", ""))


def _strip_jsonc(text: str) -> str:
    """Strip comments from repository JSONC examples before parsing them."""
    out: List[str] = []
    in_block = False
    for line in text.splitlines():
        if in_block:
            end = line.find("*/")
            if end < 0:
                continue
            line = line[end + 2:]
            in_block = False
        while "/*" in line:
            start = line.find("/*")
            end = line.find("*/", start + 2)
            if end < 0:
                line = line[:start]
                in_block = True
                break
            line = line[:start] + line[end + 2:]
        in_string = False
        quote = ""
        cut = None
        i = 0
        while i < len(line):
            ch = line[i]
            if in_string:
                if ch == "\\":
                    i += 2
                    continue
                if ch == quote:
                    in_string = False
            elif ch in ('"', "'"):
                in_string = True
                quote = ch
            elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                cut = i
                break
            i += 1
        out.append(line if cut is None else line[:cut])
    return "\n".join(out)


def _extract_fenced_blocks(text: str, language: str) -> List[str]:
    blocks: List[str] = []
    pattern = re.compile(
        r"```" + re.escape(language) + r"\s*\n(.*?)\n```",
        re.DOTALL,
    )
    for match in pattern.finditer(text):
        blocks.append(match.group(1))
    return blocks


class TestDocsConsistency(unittest.TestCase):
    def test_canonical_version_matches_irag_module(self):
        self.assertEqual(_load_irag_version(), _load_irag_module_version())

    def test_readme_version_badge_matches_canonical(self):
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        match = re.search(r"badge/version-([0-9]+\.[0-9]+\.[0-9]+)-", readme)
        self.assertIsNotNone(match, "README version badge not found")
        self.assertEqual(match.group(1), _load_irag_version())

    def test_docs_protocol_versions_include_all_supported(self):
        docs_text = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in DOCS.glob("*.md")
        )
        mentioned = set(re.findall(r"`(20\d{2}-\d{2}-\d{2})`", docs_text))
        self.assertFalse(set(_load_supported_versions()) - mentioned)

    def test_all_doc_json_blocks_parse(self):
        for path in DOCS.glob("*.md"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for index, block in enumerate(_extract_fenced_blocks(text, "json")):
                try:
                    json.loads(_strip_jsonc(block))
                except Exception as exc:
                    self.fail(f"{path.name} JSON block #{index} failed to parse: {exc}")

    def test_all_example_json_files_parse(self):
        for path in EXAMPLES.glob("*.json"):
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                self.fail(f"{path.name} failed to parse: {exc}")

    def test_all_example_jsonc_files_parse(self):
        for path in EXAMPLES.glob("*.jsonc"):
            try:
                json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
            except Exception as exc:
                self.fail(f"{path.name} failed to parse as JSONC: {exc}")

    def test_expected_client_examples_exist(self):
        names = {path.name for path in EXAMPLES.iterdir() if path.is_file()}
        for expected in (
            "warp.example.json",
            "opencode-v2.example.jsonc",
            "opencode-legacy.example.json",
            "jetbrains.example.json",
            "projects.example.json",
        ):
            self.assertIn(expected, names)


class TestInstallDocsMatrix(unittest.TestCase):
    INSTALL_DOCS = (
        "README.md",
        "INSTALL.md",
        "START_HERE.md",
        "docs/INSTALLATION.md",
        "docs/ZERO-SHOT-SETUP-PROMPTS.md",
        "docs/WARP-SETUP.md",
        "docs/OPENCODE.md",
        "docs/MCP-MULTI-PROJECT.md",
    )

    def _read(self, rel: str) -> str:
        return (PROJECT_ROOT / rel).read_text(encoding="utf-8")

    def test_no_stale_version_expectations(self):
        for rel in self.INSTALL_DOCS:
            text = self._read(rel)
            bad = re.findall(r"(?i)expect(?:ed)?\s*:?\s*1\.[678]\.0", text)
            self.assertFalse(bad, f"{rel} contains stale version expectations: {bad}")

    def test_readme_documents_all_clients_and_scopes(self):
        readme = self._read("README.md")
        for client in ("warp", "opencode", "opencode2", "jetbrains"):
            self.assertIn(f"--client {client}", readme)
            self.assertIn(f"--client {client} --global", readme)

    def test_install_md_warns_bare_install_is_not_registration(self):
        text = self._read("INSTALL.md")
        self.assertRegex(text, r"(?i)does \*\*not\*\*.*register|not.*register")

    def test_opencode_v1_example_is_flat_mcp(self):
        data = json.loads(self._read("examples/opencode-legacy.example.json"))
        mcp = data["mcp"]
        self.assertNotIn("servers", mcp)
        entry = mcp["mcp-light-memory"]
        self.assertEqual(entry["type"], "local")
        self.assertIsInstance(entry["command"], list)
        self.assertTrue(entry["enabled"])

    def test_opencode_v2_example_uses_mcp_servers(self):
        data = json.loads(_strip_jsonc(self._read("examples/opencode-v2.example.jsonc")))
        entry = data["mcp"]["servers"]["mcp-light-memory"]
        self.assertEqual(entry["type"], "local")
        self.assertIsInstance(entry["command"], list)
        self.assertNotIn("enabled", entry)

    def test_jetbrains_is_documented_as_assisted(self):
        install = self._read("docs/INSTALLATION.md")
        self.assertIn("no automatic registration", install)
        self.assertIn("Server level", install)
        self.assertIn("Project", install)
        self.assertIn("Global", install)

    def test_global_semantics_are_explicit(self):
        install = self._read("docs/INSTALLATION.md")
        self.assertRegex(install, r"(?i)--global.*CLIENT CONFIG")
        self.assertIn("target project", install)
        self.assertIn("multi-project router", install)


class TestAgentInstallContract(unittest.TestCase):
    def _contract(self) -> str:
        text = (DOCS / "INSTALLATION.md").read_text(encoding="utf-8")
        match = re.search(r"(?s)## Agent installation contract.*?(?=\n## )", text)
        self.assertIsNotNone(match, "Agent installation contract is missing")
        return match.group(0)

    def test_target_project_rule_is_exact(self):
        contract = self._contract()
        self.assertIn("first argument", contract)
        self.assertIn("git rev-parse --show-toplevel", contract)
        self.assertIn("cwd = TARGET_PROJECT", contract)

    def test_generic_opencode_maps_to_stable_v1(self):
        contract = self._contract()
        self.assertIn('"OpenCode", "OpenCode stable", "OpenCode V1"', contract)
        self.assertIn("`--client opencode`", contract)

    def test_opencode2_mapping_is_explicit(self):
        contract = self._contract()
        self.assertIn('"OpenCode 2", "OpenCode V2", "opencode2"', contract)
        self.assertIn("`--client opencode2`", contract)

    def test_global_for_project_does_not_mean_router(self):
        contract = self._contract()
        self.assertIn("globally for project", contract)
        self.assertRegex(contract, r"(?i)does \*\*NOT\*\* mean the multi-project router")

    def test_english_windows_examples_cover_clients(self):
        contract = self._contract()
        self.assertIn("Install the mcp-light-memory server in Warp globally", contract)
        self.assertIn('install.py "C:\\Work\\App" --client warp --global', contract)
        self.assertIn('install.py "C:\\Work\\App" --client opencode', contract)
        self.assertIn('install.py "C:\\Work\\App" --client opencode2 --global', contract)
        self.assertIn('install.py "C:\\Work\\App" --client jetbrains --global', contract)

    def test_workflow_requires_real_registration(self):
        contract = self._contract()
        for token in (
            "verify TARGET_PROJECT",
            "stable location outside",
            "mlm.py --version",
            "mlm.py status",
            "mlm.py guard",
            "report success",
            "UI/approval",
        ):
            self.assertIn(token, contract)
        self.assertRegex(contract, r"(?i)activation|approval")
        self.assertIn("MANUAL EDIT REQUIRED (JSONC)", contract)


class TestEnglishLanguagePolicy(unittest.TestCase):
    """Repository prose is English; technical identifiers remain unchanged."""

    POLISH_DIACRITICS = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")
    POLISH_PHRASES = re.compile(
        r"(?i)\b(?:dla projektu|globalnie|zainstaluj|skonfiguruj|użyj|jeśli|"
        r"narzędzie|repozytorium|pamiętaj|sprawdź|sukces|wiele projektów|"
        r"przygotuj|projektowo|nie nadpisuj|uruchom|zweryfikuj)\b"
    )
    TEXT_SUFFIXES = {".md", ".py", ".ts", ".ps1", ".yml", ".yaml"}
    SKIP_DIRS = {".git", "node_modules", "__pycache__"}

    def test_documentation_and_source_prose_is_english(self):
        offenders = []
        for path in PROJECT_ROOT.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in self.TEXT_SUFFIXES:
                continue
            if any(part in self.SKIP_DIRS for part in path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if self.POLISH_DIACRITICS.search(text) or self.POLISH_PHRASES.search(text):
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertFalse(
            offenders,
            "Non-English Polish prose found in repository text files: " + ", ".join(offenders),
        )


class TestOfflineDocsConsistency(unittest.TestCase):
    def test_readme_archive_name_matches_pack(self):
        pack = (PROJECT_ROOT / "pack.py").read_text(encoding="utf-8")
        self.assertRegex(pack, r"internal-rag-offline-\{VERSION\}\.zip")
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("internal-rag-offline-", readme)
        self.assertNotIn("mcp-light-memory-offline-", readme)

    def test_offline_doc_version_matches_canonical(self):
        text = (DOCS / "OFFLINE.md").read_text(encoding="utf-8")
        match = re.search(r"^\s*#.*?\((v?[0-9]+\.[0-9]+\.[0-9]+)\)", text)
        self.assertIsNotNone(match, "OFFLINE.md title version not found")
        self.assertEqual(match.group(1).lstrip("v"), _load_irag_version())


if __name__ == "__main__":
    unittest.main(verbosity=2)
