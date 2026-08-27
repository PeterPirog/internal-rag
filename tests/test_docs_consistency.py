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
        # A "**Version:** X.Y.Z" line, when present, must match the canonical
        # version. (The current README points at the VERSION file instead —
        # both forms are accepted.)
        m2 = re.search(r"\*\*Version:\*\*\s*([0-9]+\.[0-9]+\.[0-9]+)", readme)
        if m2 is not None:
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


class TestInstallDocsMatrix(unittest.TestCase):
    """Canonical installation contract (v1.8.1 docs alignment).

    One unambiguous contract: client x scope matrix, `--global` semantics,
    no version drift, correct OpenCode V1/V2 config shapes, JetBrains is
    assisted (never "the installer writes the config").
    """

    INSTALL_DOCS = ("README.md", "docs/INSTALLATION.md",
                    "docs/ZERO-SHOT-SETUP-PROMPTS.md", "docs/WARP-SETUP.md",
                    "docs/OPENCODE.md", "docs/MCP-MULTI-PROJECT.md")

    def _read(self, rel: str) -> str:
        return (PROJECT_ROOT / rel).read_text(encoding="utf-8")

    # ------------------------------------------------------------------ #

    def test_no_stale_version_expectations(self):
        """Installation docs must not instruct users to expect a specific
        old version (e.g. 'expect 1.7.0' / 'expect 1.8.0'); the canonical
        version comes from the VERSION file."""
        for rel in self.INSTALL_DOCS:
            text = self._read(rel)
            bad = re.findall(r"(?i)expect(?:ed)?\s*:?\s*1\.[678]\.0", text)
            self.assertFalse(bad, f"{rel} contains stale version expectations: {bad}")
            self.assertNotIn("Wersja: 1.7", text,
                             f"{rel} pins a stale version banner")

    def test_readme_shows_all_three_automatic_clients(self):
        readme = self._read("README.md")
        for client in ("--client warp", "--client opencode ", "--client opencode2"):
            self.assertIn(client, readme, f"README missing install command: {client!r}")

    def test_project_and_global_commands_documented(self):
        """Both scopes must be documented with real flags."""
        readme = self._read("README.md")
        install = self._read("docs/INSTALLATION.md")
        for client in ("warp", "opencode", "opencode2", "jetbrains"):
            self.assertIn(f"--client {client}", readme,
                          f"README matrix missing client: {client}")
            self.assertIn(f"--client {client}", install,
                          f"INSTALLATION.md missing client: {client}")
            if client != "opencode2":
                self.assertIn(f"--client {client} --global", readme,
                              f"README missing --global for {client}")
        self.assertIn("--client opencode2 --global", readme)
        self.assertIn("--global", install)

    def test_opencode_v1_example_is_flat_mcp(self):
        """examples/opencode-legacy.example.json must be real OpenCode V1:
        flat mcp.<name> (NO 'servers' sub-key), type local, command array,
        enabled: true."""
        data = json.loads(self._read("examples/opencode-legacy.example.json"))
        mcp = data["mcp"]
        self.assertNotIn("servers", mcp,
                         "V1 example must be flat mcp.<name> (no 'servers')")
        entry = mcp["mcp-light-memory"]
        self.assertEqual(entry["type"], "local")
        self.assertIsInstance(entry["command"], list)
        self.assertTrue(entry["enabled"])

    def test_opencode_v2_example_is_mcp_servers(self):
        """examples/opencode-v2.example.jsonc must be real OpenCode V2:
        mcp.servers.<name>, command array, and NO 'enabled' field."""
        text = self._read("examples/opencode-v2.example.jsonc")
        data = json.loads(_strip_jsonc(text))
        mcp = data["mcp"]
        self.assertIn("servers", mcp,
                      "V2 example must use mcp.servers.<name>")
        entry = mcp["servers"]["mcp-light-memory"]
        self.assertEqual(entry["type"], "local")
        self.assertIsInstance(entry["command"], list)
        self.assertNotIn("enabled", entry,
                         "V2 must not use 'enabled' (V2 uses 'disabled')")

    def test_jetbrains_docs_never_claim_auto_config_write(self):
        """JetBrains/PyCharm docs must present the setup as assisted/manual:
        the installer must not be described as writing the IDE config or
        'fully automatic' for the IDE step."""
        for rel in ("docs/INSTALLATION.md", "docs/ZERO-SHOT-SETUP-PROMPTS.md"):
            text = self._read(rel)
            self.assertNotIn("register the MCP server in ~/.jetbrains/mcp.json", text,
                             f"{rel} claims the installer writes the JetBrains config")
        install = self._read("docs/INSTALLATION.md")
        self.assertIn("no automatic registration", install)
        self.assertIn("Server level", install)
        # Both IDE server levels must be documented.
        self.assertIn("Project", install)
        self.assertIn("Global", install)

    def test_global_semantics_explained(self):
        """--global must be explained as a CLIENT CONFIG scope: the server
        stays bound to the target project, and multi-repo needs point to the
        router."""
        install = self._read("docs/INSTALLATION.md")
        self.assertIn("--global", install)
        self.assertRegex(install, r"(?i)client\s+config")
        self.assertRegex(install, r"(?i)target\s+project")
        self.assertIn("multi-project router", install)
        readme = self._read("README.md")
        self.assertRegex(readme, r"(?i)\-\-global.*?CLIENT CONFIG")

    def test_readme_opencode_section_not_mcp_servers(self):
        """README's OpenCode stable (V1) description must not show the V2
        'mcp.servers' shape as if it were V1."""
        readme = self._read("README.md")
        m = re.search(r"### OpenCode stable \(V1\)(.*?)### OpenCode 2", readme, re.S)
        self.assertIsNotNone(m, "README OpenCode V1 section not found")
        v1_section = m.group(1)
        self.assertNotIn("mcp.servers", v1_section,
                         "README V1 section must not describe mcp.servers shape")
        self.assertIn("enabled: true", v1_section)


class TestTopLevelInstallDocs(unittest.TestCase):
    """INSTALL.md / START_HERE.md must not suggest `install.py PROJECT`
    (without --client) is a complete Warp/OpenCode MCP installation."""

    def _read(self, rel: str) -> str:
        return (PROJECT_ROOT / rel).read_text(encoding="utf-8")

    def test_install_md_exists_and_links_to_canonical(self):
        text = self._read("INSTALL.md")
        self.assertIn("docs/INSTALLATION.md", text,
                       "INSTALL.md must link to the canonical guide")

    def test_install_md_lists_all_clients(self):
        text = self._read("INSTALL.md")
        for client in ("--client warp", "--client opencode",
                       "--client opencode2", "--client jetbrains"):
            self.assertIn(client, text, f"INSTALL.md missing {client}")

    def test_install_md_explains_project_global_scope(self):
        text = self._read("INSTALL.md")
        self.assertIn("--global", text)
        self.assertRegex(text, r"(?i)global.*?client config|client config.*?global")
        self.assertRegex(text, r"(?i)target project|project.*?first argument")
        self.assertRegex(text, r"(?i)not a multi-project router|multi-project router",
                         "INSTALL.md must clarify --global != router")

    def test_install_md_warns_bare_install_is_incomplete(self):
        text = self._read("INSTALL.md")
        self.assertRegex(text, r"(?i)does \*\*not\*\*\s*\n?register|not.*register",
                         "INSTALL.md must state that bare install.py is not a full MCP install")

    def test_start_here_never_shows_client_install_without_client_flag(self):
        """Any install.py invocation line in START_HERE.md that mentions a
        client (warp/opencode/jetbrains) must carry --client; and the doc
        must not present a bare `install.py <path>` line as the primary
        Warp/OpenCode install command."""
        text = self._read("START_HERE.md")
        for line in text.splitlines():
            if "install.py" in line and re.search(r"(?i)warp|opencode|jetbrains|pycharm", line):
                self.assertIn("--client", line,
                              f"client-mentioning install line lacks --client: {line.strip()}")
        # The primary install command must carry --client.
        m = re.search(r"`?\s*(?:python3?\.? ?\\?install\.py)[^\n]*`(.*?)\n", text)
        install_lines = [l for l in text.splitlines() if "install.py" in l and "unregister" not in l]
        self.assertTrue(any("--client" in l for l in install_lines),
                        "START_HERE.md primary install command lacks --client")

    def test_start_here_uses_mlm_py_not_legacy_irag_py(self):
        text = self._read("START_HERE.md")
        self.assertIn("mlm.py", text, "START_HERE.md must use primary mlm.py")
        self.assertNotIn("irag.py", text,
                         "START_HERE.md must not promote legacy irag.py as the main path")


class TestAgentInstallContract(unittest.TestCase):
    """The canonical Agent installation contract (docs/INSTALLATION.md)."""

    def _contract(self) -> str:
        text = (PROJECT_ROOT / "docs" / "INSTALLATION.md").read_text(encoding="utf-8")
        m = re.search(r"(?s)## Agent installation contract.*?(?=\n## )", text)
        self.assertIsNotNone(m, "docs/INSTALLATION.md missing '## Agent installation contract'")
        return m.group(0)

    def test_contract_exists(self):
        self.assertTrue(self._contract())

    def test_target_project_rule_is_exact(self):
        c = self._contract()
        self.assertIn("first argument", c)
        self.assertIn("git rev-parse --show-toplevel", c)
        self.assertIn("cwd = TARGET_PROJECT", c)

    def test_generic_opencode_maps_to_opencode_flag(self):
        c = self._contract()
        self.assertIn('"OpenCode", "OpenCode stable", "OpenCode V1"', c)
        self.assertIn("`--client opencode`", c)

    def test_opencode2_maps_to_opencode2_flag(self):
        c = self._contract()
        self.assertIn('"OpenCode 2", "OpenCode V2", "opencode2"', c)
        self.assertIn("`--client opencode2`", c)

    def test_global_does_not_mean_router(self):
        c = self._contract()
        self.assertIn("globalnie dla projektu", c)
        self.assertRegex(c, r"(?i)does \*\*NOT\*\* mean the multi-project router")

    def test_polish_example_with_windows_path(self):
        c = self._contract()
        self.assertIn("Zainstaluj w Warp server mcp-light-memory globalnie", c)
        self.assertIn("C:\\Work\\App", c)
        self.assertIn('install.py "C:\\Work\\App" --client warp --global', c)

    def test_en_openCode_examples(self):
        c = self._contract()
        self.assertIn('install.py "C:\\Work\\App" --client opencode', c)
        self.assertIn('install.py "C:\\Work\\App" --client opencode2 --global', c)
        self.assertIn('install.py "C:\\Work\\App" --client jetbrains --global', c)

    def test_agent_workflow_steps(self):
        c = self._contract()
        for token in ("verify TARGET_PROJECT", "stable location outside",
                      "never", "mlm.py --version", "mlm.py status", "mlm.py guard",
                      "report success", "UI/approval"):
            self.assertIn(token, c, f"agent workflow missing step: {token!r}")

    def test_warp_activation_noted(self):
        c = self._contract()
        self.assertRegex(c, r"(?i)activation|approval",
                         "contract must note Warp project-scoped activation")

    def test_jsonc_manual_required_noted(self):
        c = self._contract()
        self.assertIn("MANUAL EDIT REQUIRED (JSONC)", c)


class TestOfflineDocsConsistency(unittest.TestCase):
    """README offline archive name must match pack.py's actual naming, and
    docs/OFFLINE.md must not carry a stale version pin."""

    def _pack_naming(self) -> str:
        pack = (PROJECT_ROOT / "pack.py").read_text(encoding="utf-8")
        m = re.search(r'internal-rag-offline-\{VERSION\}\.zip', pack)
        self.assertIsNotNone(m, "pack.py default ZIP naming not found")
        return "internal-rag-offline-"

    def test_readme_offline_archive_name_matches_pack(self):
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(self._pack_naming(), readme,
                      "README offline archive must use pack.py's internal-rag-offline-<version> naming")
        self.assertNotIn("mcp-light-memory-offline-", readme,
                         "README must not use a drifted offline archive name")

    def test_offline_md_version_matches_canonical(self):
        v = _load_irag_version()
        off = (PROJECT_ROOT / "docs" / "OFFLINE.md").read_text(encoding="utf-8")
        m = re.search(r"^\s*#.*?\((v?[0-9]+\.[0-9]+\.[0-9]+)\)", off)
        self.assertIsNotNone(m, "OFFLINE.md title version not found")
        self.assertEqual(m.group(1).lstrip("v"), v,
                         f"OFFLINE.md version {m.group(1)} != canonical {v}")

    def test_offline_md_archive_name_matches_pack(self):
        off = (PROJECT_ROOT / "docs" / "OFFLINE.md").read_text(encoding="utf-8")
        self.assertIn("internal-rag-offline-", off)
        self.assertNotIn("mcp-light-memory-offline-", off)


if __name__ == "__main__":
    unittest.main(verbosity=2)