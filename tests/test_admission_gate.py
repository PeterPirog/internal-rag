#!/usr/bin/env python3
"""B regression: relevance/admission gate + abstention metadata.

Covers:
- `_admission_gate` decisions per mode (sparse/dense/hybrid)
- `search_with_meta` abstention semantics: no evidence -> abstained,
  token match -> admitted with confidence in [0, 1]
- per-candidate explain carries `admission`/`admission_reason`
"""
from __future__ import annotations
import importlib.util
import shutil
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


class Env:
    def __init__(self, sandbox: Path):
        self.sandbox = sandbox
        self.rag = sandbox / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures", "hypotheses",
                  "sessions/.snapshots", "archive"):
            (self.rag / d).mkdir(parents=True, exist_ok=True)
        (self.rag / "WORKING_STATE.md").write_text("# Working state\n", encoding="utf-8")

    def write_memory(self, name: str, title: str, body: str) -> Path:
        p = self.rag / "knowledge" / name
        fm = (f"---\nid: mem-{name[:-3]}\ntype: knowledge\nstatus: active\n"
              "created: 2024-01-01\nscope: []\ntags: []\n---\n\n"
              f"# {title}\n\n## Knowledge\n\n{body}\n\n## Consequence\n\nNone.\n")
        p.write_text(fm, encoding="utf-8")
        return p

    def __enter__(self):
        self._old = (irag.ROOT, irag.RAG, irag.CONFIG_PATH, irag.WORKING,
                     irag._open_sqlite_index)
        irag.ROOT = self.sandbox
        irag.RAG = self.rag
        irag.CONFIG_PATH = self.sandbox / ".irag.yml"
        irag.WORKING = self.rag / "WORKING_STATE.md"
        irag._open_sqlite_index = lambda: None
        return self

    def __exit__(self, *a):
        irag.ROOT, irag.RAG, irag.CONFIG_PATH, irag.WORKING, irag._open_sqlite_index = self._old


def _cfg(**retrieval_overrides) -> Dict[str, Any]:
    retrieval = {
        "limit": 5, "mmr_lambda": 0.5, "min_score": 0.0, "mode": "sparse",
        "embeddings": "off", "rrf_k": 60, "sparse_weight": 1.0, "dense_weight": 1.0,
        "candidate_multiplier": 4, "pl_stopwords": False,
        "abstention": {"enabled": True, "require_sparse_match": True, "min_dense_score": None},
        "fts_prefilter": {"enabled": False, "min_corpus_size": 50},
    }
    retrieval.update(retrieval_overrides)
    return {"retrieval": retrieval}


class TestAdmissionGateUnit(unittest.TestCase):
    def test_sparse_passes_on_token_match(self):
        ok, why = irag._admission_gate({"sparse_rank": 1}, ["postgres"],
                                       "we use postgres here", {"mode": "sparse"}, ["postgres"])
        self.assertTrue(ok)
        self.assertEqual(why, "sparse_token_match")

    def test_sparse_rejects_without_token_match(self):
        ok, why = irag._admission_gate({"sparse_rank": 1}, [],
                                       "completely unrelated text", {"mode": "sparse"}, ["postgres"])
        self.assertFalse(ok)
        self.assertEqual(why, "sparse_no_token_match")

    def test_sparse_no_evidence(self):
        ok, why = irag._admission_gate({}, [], "nothing", {"mode": "sparse"}, ["postgres"])
        self.assertFalse(ok)
        self.assertEqual(why, "no_sparse_evidence")

    def test_dense_respects_min_score(self):
        below, why_b = irag._admission_gate({"dense_score": 0.1}, [], "x",
                                            {"mode": "dense", "min_dense_score": 0.5}, [])
        self.assertFalse(below)
        self.assertIn("dense_below_min_score", why_b)
        above, why_a = irag._admission_gate({"dense_score": 0.9}, [], "x",
                                            {"mode": "dense", "min_dense_score": 0.5}, [])
        self.assertTrue(above)
        self.assertEqual(why_a, "dense_evidence")

    def test_dense_null_threshold_accepts(self):
        ok, why = irag._admission_gate({"dense_score": 0.05}, [], "x",
                                       {"mode": "dense", "min_dense_score": None}, [])
        self.assertTrue(ok, why)

    def test_hybrid_either_channel(self):
        ok, why = irag._admission_gate({"sparse_rank": 3}, ["postgres"],
                                       "has postgres in it", {"mode": "hybrid"}, ["postgres"])
        self.assertTrue(ok)
        ok2, _ = irag._admission_gate({"dense_score": 0.3}, [], "unrelated", {"mode": "hybrid"}, ["zzz"])
        self.assertTrue(ok2)
        ok3, why3 = irag._admission_gate({}, [], "totally unrelated", {"mode": "hybrid"}, ["zzz"])
        self.assertFalse(ok3)
        self.assertEqual(why3, "no_retrieval_evidence")


class TestAbstentionMeta(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="irag-abstain-"))
        self.env = Env(self.tmp)
        self.env.__enter__()

    def tearDown(self):
        self.env.__exit__(None, None, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_results_abstains(self):
        self.env.write_memory("a.md", "Alpha", "alpha body text")
        c = _cfg()
        results = irag._search_with_cfg("zzz_nonexistent_token_xyz", 5, c)
        meta = c["_abstention_meta"]
        self.assertEqual(results, [])
        self.assertTrue(meta["abstained"])
        self.assertEqual(meta["retrieval_confidence"], 0.0)

    def test_token_match_admitted_with_confidence(self):
        self.env.write_memory("a.md", "Alpha", "we provision the postgres cluster")
        c = _cfg()
        results = irag._search_with_cfg("postgres cluster", 5, c)
        meta = c["_abstention_meta"]
        self.assertTrue(results)
        self.assertFalse(meta["abstained"])
        self.assertGreaterEqual(meta["retrieval_confidence"], 0.0)
        self.assertLessEqual(meta["retrieval_confidence"], 1.0)
        self.assertGreaterEqual(meta["admitted"], 1)

    def test_explain_carries_admission_reason(self):
        self.env.write_memory("a.md", "Alpha", "we provision the postgres cluster")
        c = _cfg()
        results = irag._search_with_cfg("postgres cluster", 5, c, explain=True)
        self.assertTrue(results)
        fm = results[0][2]
        self.assertIn("_explain", fm)
        self.assertIn("admission", fm["_explain"])
        self.assertIn("admission_reason", fm["_explain"])
        self.assertTrue(fm["_explain"]["admission"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
