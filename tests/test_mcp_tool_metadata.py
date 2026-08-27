#!/usr/bin/env python3
"""Regression tests for MCP tool metadata exposed through tools/list."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent
IRAG = ROOT / ".agents" / "skills" / "internal-rag" / "irag.py"

EXPECTED_TITLES = {
    "context": "Load Task Context",
    "search": "Search Project Memory",
    "checkpoint": "Save Task Checkpoint",
    "guard": "Check Checkpoint Freshness",
    "remember": "Store Durable Memory",
    "status": "Inspect Memory Status",
    "tasks": "List Pending Tasks",
    "resume": "Resume Saved Task",
}


def _tools_list() -> List[Dict[str, Any]]:
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "metadata-test", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}},
    ]
    proc = subprocess.run(
        [sys.executable, str(IRAG), "mcp"],
        cwd=str(ROOT),
        input="\n".join(json.dumps(item) for item in requests) + "\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(f"MCP server failed: {proc.stderr}")
    responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    listing = next(item for item in responses if item.get("id") == 2)
    return listing["result"]["tools"]


class TestMcpToolMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tools = {tool["name"]: tool for tool in _tools_list()}

    def test_all_core_tools_have_stable_titles(self) -> None:
        for name, title in EXPECTED_TITLES.items():
            self.assertIn(name, self.tools)
            self.assertEqual(self.tools[name].get("title"), title)

    def test_descriptions_explain_behavior_without_annotation_contradictions(self) -> None:
        for name in EXPECTED_TITLES:
            description = self.tools[name].get("description", "")
            self.assertGreaterEqual(len(description), 80, name)
            self.assertIn("network", description.lower(), name)

        for name in ("guard", "status", "tasks"):
            tool = self.tools[name]
            self.assertTrue(tool["annotations"]["readOnlyHint"], name)
            self.assertTrue(tool["annotations"]["idempotentHint"], name)
            self.assertIn("read-only", tool["description"].lower(), name)
            self.assertIn("idempotent", tool["description"].lower(), name)

        for name in ("context", "checkpoint", "remember", "resume"):
            tool = self.tools[name]
            self.assertFalse(tool["annotations"]["readOnlyHint"], name)
            self.assertFalse(tool["annotations"]["idempotentHint"], name)

        search = self.tools["search"]
        self.assertTrue(search["annotations"]["readOnlyHint"])
        self.assertFalse(search["annotations"]["idempotentHint"])
        self.assertIn("not marked idempotent", search["description"].lower())

    def test_parameter_descriptions_cover_nontrivial_inputs(self) -> None:
        expected = {
            "context": ("task", "limit"),
            "search": ("query", "limit", "types", "statuses", "at", "explain"),
            "checkpoint": ("reason", "phase", "completed", "in_progress", "blockers", "next"),
            "remember": ("type", "title", "body", "tags", "evidence", "scope", "consequence", "status"),
        }
        for tool_name, property_names in expected.items():
            properties = self.tools[tool_name]["inputSchema"]["properties"]
            for property_name in property_names:
                self.assertTrue(properties[property_name].get("description"),
                                f"{tool_name}.{property_name}")

    def test_existing_output_schemas_have_property_descriptions(self) -> None:
        for name in ("search", "guard", "status", "tasks"):
            output_schema = self.tools[name].get("outputSchema")
            self.assertIsInstance(output_schema, dict, name)
            properties = output_schema.get("properties", {})
            self.assertTrue(properties, name)
            for property_name, property_schema in properties.items():
                self.assertTrue(property_schema.get("description"),
                                f"{name}.{property_name}")

    def test_enrichment_preserves_input_contract(self) -> None:
        search = self.tools["search"]["inputSchema"]
        self.assertEqual(search["properties"]["limit"]["minimum"], 1)
        self.assertEqual(search["properties"]["limit"]["maximum"], 50)
        self.assertEqual(search["properties"]["limit"]["default"], 8)
        self.assertEqual(search["required"], ["query"])

        remember = self.tools["remember"]["inputSchema"]
        self.assertEqual(remember["required"], ["type", "title", "body"])
        self.assertIn("decision", remember["properties"]["type"]["enum"])
        self.assertIn("tentative", remember["properties"]["status"]["enum"])


if __name__ == "__main__":
    unittest.main()
