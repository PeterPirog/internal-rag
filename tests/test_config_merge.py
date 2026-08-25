#!/usr/bin/env python3
"""A2 regression: config deep-merge + YAML-subset parser.

Covers:
- deep_merge: override wins per leaf; nested dicts merge; an override of one
  leaf NEVER removes sibling defaults (the core A2 guarantee)
- deep_merge does not mutate the base unexpectedly and handles type conflicts
- parse_yaml_simple: nested mappings, inline lists, block lists, scalars,
  comments; fallback to JSON for pure-JSON input
- load_config: file config over built-in defaults with full sibling retention
- _validate_config: fts_prefilter + abstention field validation (already wired)
"""
from __future__ import annotations
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
IRAG_PATH = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag.py"

_spec = importlib.util.spec_from_file_location("irag_mod", str(IRAG_PATH))
irag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(irag)


class TestDeepMerge(unittest.TestCase):
    def test_override_wins_per_leaf(self):
        base = {"a": 1, "b": 2}
        out = irag.deep_merge(dict(base), {"b": 99})
        self.assertEqual(out, {"a": 1, "b": 99})

    def test_nested_merge_keeps_siblings(self):
        base = {"r": {"x": 1, "y": 2, "z": 3}}
        out = irag.deep_merge(dict(base), {"r": {"y": 99}})
        self.assertEqual(out, {"r": {"x": 1, "y": 99, "z": 3}})

    def test_deep_nested_sibling_retention(self):
        base = {"a": {"b": {"c": 1, "d": 2, "e": 3}}}
        out = irag.deep_merge(dict(base), {"a": {"b": {"d": 42}}})
        self.assertEqual(out, {"a": {"b": {"c": 1, "d": 42, "e": 3}}})

    def test_override_of_one_leaf_keeps_siblings(self):
        """The core A2 guarantee: overriding retrieval.fts_prefilter.enabled
        must not drop retrieval.fts_prefilter.min_corpus_size or other keys."""
        base = {"r": {"fts": {"enabled": True, "min": 50}, "other": 1}}
        out = irag.deep_merge(dict(base), {"r": {"fts": {"enabled": False}}})
        self.assertEqual(out, {"r": {"fts": {"enabled": False, "min": 50}, "other": 1}})

    def test_type_conflict_override_wins(self):
        base = {"k": {"nested": 1}}
        out = irag.deep_merge(dict(base), {"k": "scalar"})
        self.assertEqual(out, {"k": "scalar"})
        base2 = {"k": "scalar"}
        out2 = irag.deep_merge(dict(base2), {"k": {"nested": 1}})
        self.assertEqual(out2, {"k": {"nested": 1}})

    def test_default_config_sibling_retention(self):
        """Overriding a single leaf of the REAL default config must retain
        every other default in that subtree."""
        base = json.loads(json.dumps(irag.DEFAULT_CONFIG))
        override = {"retrieval": {"abstention": {"enabled": False}}}
        out = irag.deep_merge(base, override)
        self.assertFalse(out["retrieval"]["abstention"]["enabled"])
        self.assertIn("require_sparse_match", out["retrieval"]["abstention"])
        self.assertIn("min_dense_score", out["retrieval"]["abstention"])
        self.assertIn("limit", out["retrieval"])
        self.assertIn("mode", out["retrieval"])
        self.assertIn("tokens", out)


class TestParseYaml(unittest.TestCase):
    def test_nested_mapping(self):
        txt = "retrieval:\n  limit: 5\n  fts_prefilter:\n    enabled: true\n    min_corpus_size: 50\n"
        d = irag.parse_yaml_simple(txt)
        self.assertEqual(d["retrieval"]["limit"], 5)
        self.assertTrue(d["retrieval"]["fts_prefilter"]["enabled"])
        self.assertEqual(d["retrieval"]["fts_prefilter"]["min_corpus_size"], 50)

    def test_inline_and_block_lists(self):
        d = irag.parse_yaml_simple("a: [x, y]\nb:\n  - 1\n  - 2\n")
        self.assertEqual(d["a"], ["x", "y"])
        self.assertEqual(d["b"], [1, 2])

    def test_scalars_and_comments(self):
        d = irag.parse_yaml_simple("# comment\nx: true\ny: false\nz: null\nn: 3\nf: 1.5\ns: hello\n")
        self.assertIs(d["x"], True)
        self.assertIs(d["y"], False)
        self.assertIsNone(d["z"])
        self.assertEqual(d["n"], 3)
        self.assertEqual(d["f"], 1.5)
        self.assertEqual(d["s"], "hello")

    def test_json_fallback(self):
        d = irag.parse_yaml_simple('{"a": {"b": 1}}')
        self.assertEqual(d, {"a": {"b": 1}})


class TestLoadConfig(unittest.TestCase):
    def test_file_override_retains_defaults(self):
        old = irag.CONFIG_PATH
        try:
            with tempfile.TemporaryDirectory() as td:
                cfgp = Path(td) / ".irag.yml"
                cfgp.write_text("retrieval:\n  limit: 42\n", encoding="utf-8")
                irag.CONFIG_PATH = cfgp
                cfg = irag.load_config()
                self.assertEqual(cfg["retrieval"]["limit"], 42)
                self.assertIn("mode", cfg["retrieval"])
                self.assertIn("fts_prefilter", cfg["retrieval"])
                self.assertIn("tokens", cfg)
        finally:
            irag.CONFIG_PATH = old


class TestValidateConfig(unittest.TestCase):
    def test_valid_config_passes(self):
        cfg = json.loads(json.dumps(irag.DEFAULT_CONFIG))
        issues = irag._validate_config(cfg)
        self.assertEqual(issues, [])

    def test_bad_fts_prefilter_flagged(self):
        cfg = json.loads(json.dumps(irag.DEFAULT_CONFIG))
        cfg["retrieval"]["fts_prefilter"]["enabled"] = "yes"
        issues = irag._validate_config(cfg)
        self.assertTrue(any("fts_prefilter.enabled" in i for i in issues))

    def test_bad_min_corpus_size_flagged(self):
        cfg = json.loads(json.dumps(irag.DEFAULT_CONFIG))
        cfg["retrieval"]["fts_prefilter"]["min_corpus_size"] = -1
        issues = irag._validate_config(cfg)
        self.assertTrue(any("fts_prefilter.min_corpus_size" in i for i in issues))


if __name__ == "__main__":
    unittest.main(verbosity=2)
