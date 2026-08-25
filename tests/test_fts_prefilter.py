#!/usr/bin/env python3
"""Tests for the C: FTS5 candidate prefilter.

Acceptance criteria:
- with the prefilter enabled, search results are IDENTICAL to the full
  Python BM25 scan (the prefilter is a union accelerator — it narrows the
  scoring pool, it never changes the ranking)
- stale index (memory file newer than the index) falls back to the full scan
- config switches (enabled=false, min_corpus_size) are respected
- FTS5 matching nothing falls back to the full scan (no empty results)
"""
from __future__ import annotations
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Tuple

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
SKILL_DIR = PROJECT_ROOT / ".agents" / "skills" / "internal-rag"
IRAG_PATH = SKILL_DIR / "irag.py"
INDEX_PATH = SKILL_DIR / "irag_index.py"

_spec = importlib.util.spec_from_file_location("irag_mod", str(IRAG_PATH))
irag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(irag)

_spec_idx = importlib.util.spec_from_file_location("irag_index_mod", str(INDEX_PATH))
irag_index = importlib.util.module_from_spec(_spec_idx)
_spec_idx.loader.exec_module(irag_index)

CORPUS_SIZE = 60


def _base_cfg(**retrieval_overrides) -> Dict[str, Any]:
    retrieval = {
        "limit": 5,
        "mmr_lambda": 0.5,
        "min_score": 0.0,
        "mode": "sparse",
        "embeddings": "off",
        "rrf_k": 60,
        "sparse_weight": 1.0,
        "dense_weight": 1.0,
        "candidate_multiplier": 4,
        "bm25_k1": 1.5,
        "bm25_b": 0.75,
        "pl_stopwords": False,
        "fts_prefilter": {"enabled": True, "min_corpus_size": 50},
    }
    retrieval.update(retrieval_overrides)
    return {"retrieval": retrieval}


class FtsPrefilterEnv:
    def __init__(self, sandbox: Path):
        self.sandbox = sandbox
        self.rag = sandbox / "INTERNAL_RAG" / "knowledge"
        self.rag.mkdir(parents=True)
        (sandbox / "INTERNAL_RAG" / "WORKING_STATE.md").parent.mkdir(parents=True, exist_ok=True)
        (sandbox / "INTERNAL_RAG" / "WORKING_STATE.md").write_text("# Working state\n", encoding="utf-8")

    def write_memories(self, n: int = CORPUS_SIZE) -> None:
        for i in range(n):
            topic = "widget_alpha" if i % 2 == 0 else "widget_beta"
            filler = f"neutral context number {i} about retrieval pipelines"
            text = (
                "---\n"
                f"id: mem-pf-{i:03d}\n"
                "type: knowledge\nstatus: active\n"
                "created: 2024-01-01\nscope: []\ntags: []\n"
                "---\n\n"
                f"# Memory {i}\n\n## Knowledge\n\n"
                f"Configuration for {topic} uses a fixed cadence. {filler}\n\n"
                "## Consequence\n\nNone.\n"
            )
            (self.rag / f"mem-{i:03d}.md").write_text(text, encoding="utf-8")

    def __enter__(self):
        self._old = (irag.ROOT, irag.RAG, irag.CONFIG_PATH, irag.WORKING,
                     irag._open_sqlite_index)
        irag.ROOT = self.sandbox
        irag.RAG = self.sandbox / "INTERNAL_RAG"
        irag.CONFIG_PATH = self.sandbox / ".irag.yml"
        irag.WORKING = irag.RAG / "WORKING_STATE.md"
        irag._open_sqlite_index = lambda: None
        return self

    def build_index(self):
        idx = irag_index.IndexDB(irag.RAG / ".index.sqlite3", irag.ROOT)
        idx.migrate()
        cands = [(p, p.read_text(encoding="utf-8"), irag.parse_fm(p.read_text(encoding="utf-8")))
                 for p in sorted(self.rag.glob("*.md"))]
        idx.rebuild(cands)
        self._idx = idx
        irag._open_sqlite_index = lambda: idx
        return idx

    def __exit__(self, *a):
        idx = getattr(self, "_idx", None)
        if idx is not None:
            try:
                idx.close()
            except Exception:
                pass
        irag.ROOT, irag.RAG, irag.CONFIG_PATH, irag.WORKING, irag._open_sqlite_index = self._old


def _ids(results) -> list:
    return [str(fm.get("id", "")) for _s, _p, fm, _sn in results]


class TestPrefilterParity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="irag-pf-parity-"))
        self.env = FtsPrefilterEnv(self.tmp)
        self.env.__enter__()
        self.env.write_memories()

    def tearDown(self):
        self.env.__exit__(None, None, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_results_identical_with_prefilter(self):
        """Enabled prefilter must produce the exact same top-k as the full scan."""
        self.env.build_index()
        cfg_on = _base_cfg(fts_prefilter={"enabled": True, "min_corpus_size": 50})
        cfg_off = _base_cfg(fts_prefilter={"enabled": False, "min_corpus_size": 50})
        seen_on = None
        seen_off = None
        for q in ("widget_alpha cadence", "configuration retrieval pipelines",
                  "widget_beta fixed", "neutral context number"):
            c_on = dict(cfg_on)
            c_off = dict(cfg_off)
            r_on = irag._search_with_cfg(q, 5, c_on)
            r_off = irag._search_with_cfg(q, 5, c_off)
            self.assertEqual(_ids(r_on), _ids(r_off), f"parity broken for query: {q!r}")
            seen_on = c_on.get("_fts_prefilter")
            seen_off = c_off.get("_fts_prefilter")
        self.assertEqual(seen_on, "used")
        self.assertEqual(seen_off, "skipped")

    def test_small_corpus_skips_prefilter(self):
        """Below min_corpus_size the prefilter is skipped (tiny-corpus overhead guard)."""
        self.env.build_index()
        cfg = _base_cfg(fts_prefilter={"enabled": True, "min_corpus_size": 100000})
        r = irag._search_with_cfg("widget_alpha", 5, cfg)
        self.assertEqual(cfg.get("_fts_prefilter"), "skipped")
        self.assertTrue(r)

    def test_stale_index_falls_back(self):
        """A memory newer than the index must disable the prefilter (freshness guard)."""
        self.env.build_index()
        victim = sorted(self.env.rag.glob("*.md"))[0]
        import time as _t
        _t.sleep(0.02)
        victim.write_text(victim.read_text(encoding="utf-8") + "\n<!-- touched -->\n", encoding="utf-8")
        cfg = _base_cfg(fts_prefilter={"enabled": True, "min_corpus_size": 50})
        r = irag._search_with_cfg("widget_alpha", 5, cfg)
        self.assertEqual(cfg.get("_fts_prefilter"), "skipped")
        self.assertTrue(r)

    def test_no_fresh_index_falls_back(self):
        """Without an index file at all, search must still work (full scan)."""
        cfg = _base_cfg(fts_prefilter={"enabled": True, "min_corpus_size": 50})
        r = irag._search_with_cfg("widget_alpha", 5, cfg)
        self.assertEqual(cfg.get("_fts_prefilter"), "skipped")
        self.assertTrue(r)
        ids = _ids(r)
        self.assertTrue(all(i.startswith("mem-pf-") for i in ids))

    def test_prefilter_helper_disabled(self):
        """_fts_prefilter_paths returns None when disabled or corpus is small."""
        idx = self.env.build_index()
        cands = [(p, p.read_text(encoding="utf-8"), irag.parse_fm(p.read_text(encoding="utf-8")))
                 for p in sorted(self.env.rag.glob("*.md"))]
        cfg = _base_cfg(fts_prefilter={"enabled": False, "min_corpus_size": 50})
        self.assertIsNone(irag._fts_prefilter_paths("widget_alpha", cfg, cands, 100))
        cfg = _base_cfg(fts_prefilter={"enabled": True, "min_corpus_size": 50})
        kept = irag._fts_prefilter_paths("widget_alpha", cfg, cands, 100)
        self.assertIsNotNone(kept)
        self.assertGreater(len(kept), 0)
        self.assertLessEqual(len(kept), 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
