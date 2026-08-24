#!/usr/bin/env python3
"""Tests for section-aware chunking.

Uses only the standard library (unittest). No external dependencies.
"""
from __future__ import annotations
import hashlib
import importlib.util
import tempfile
import shutil
import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
IRAG_PATH = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag.py"
INDEX_PATH = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag_index.py"
FIXTURES_DIR = HERE / "fixtures" / "retrieval"

_spec = importlib.util.spec_from_file_location("irag_mod", str(IRAG_PATH))
irag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(irag)

_spec_idx = importlib.util.spec_from_file_location("irag_index_mod", str(INDEX_PATH))
irag_index = importlib.util.module_from_spec(_spec_idx)
_spec_idx.loader.exec_module(irag_index)


def _make_fm(mem_id: str = "test-mem", mtype: str = "knowledge",
             status: str = "active", tags: list = None, scope: list = None) -> Dict[str, Any]:
    return {
        "id": mem_id, "type": mtype, "status": status,
        "created": "2024-01-01", "tags": tags or [], "scope": scope or [],
    }


def _make_memory(mem_id: str, title: str, body: str, fm: Dict[str, Any] = None) -> str:
    fm = fm or _make_fm(mem_id)
    tags = fm.get("tags", [])
    scope = fm.get("scope", [])
    tags_yaml = "tags: []\n" if not tags else "tags:\n" + "".join(f"  - {t}\n" for t in tags)
    scope_yaml = "scope: []\n" if not scope else "scope:\n" + "".join(f"  - {s}\n" for s in scope)
    return (
        f"---\nid: {mem_id}\ntype: {fm.get('type', 'knowledge')}\n"
        f"status: {fm.get('status', 'active')}\n"
        f"created: {fm.get('created', '2024-01-01')}\n"
        f"{tags_yaml}{scope_yaml}---\n\n"
        f"# {title}\n\n## Knowledge\n\n{body}\n\n## Consequence\n\nNone.\n"
    )


class TestChunkMemory(unittest.TestCase):

    def test_short_memory_one_chunk(self):
        """Memory shorter than threshold should produce exactly 1 chunk."""
        fm = _make_fm("mem-short", tags=["test"])
        text = _make_memory("mem-short", "Short Title", "This is a short body.")
        chunks = irag_index.chunk_memory("mem-short", text, fm)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0][0], "mem-short:full:0")
        self.assertEqual(chunks[0][1], "full")

    def test_long_memory_multiple_chunks(self):
        """Long memory with 3 headings should produce multiple chunks."""
        body = "## Section A\n\n" + "A" * 800 + "\n\n## Section B\n\n" + "B" * 800 + "\n\n## Section C\n\n" + "C" * 800
        fm = _make_fm("mem-long", tags=["test"])
        text = _make_memory("mem-long", "Long Memory", body)
        chunks = irag_index.chunk_memory("mem-long", text, fm,
                                          {"enabled": True, "threshold_chars": 200,
                                           "target_chars": 1200, "overlap_chars": 120})
        self.assertGreater(len(chunks), 1)
        # Each chunk should have a section slug
        sections = set(c[1] for c in chunks)
        self.assertGreater(len(sections), 1)

    def test_chunk_id_deterministic(self):
        """Chunk IDs should be deterministic for the same input."""
        fm = _make_fm("mem-det", tags=["test"])
        text = _make_memory("mem-det", "Deterministic", "## A\n\nContent A\n\n## B\n\nContent B")
        chunks1 = irag_index.chunk_memory("mem-det", text, fm)
        chunks2 = irag_index.chunk_memory("mem-det", text, fm)
        ids1 = [c[0] for c in chunks1]
        ids2 = [c[0] for c in chunks2]
        self.assertEqual(ids1, ids2)

    def test_chunk_content_hash_deterministic(self):
        """Chunk content hashes should be deterministic."""
        fm = _make_fm("mem-hash", tags=["test"])
        text = _make_memory("mem-hash", "Hash Test", "Some content here.")
        chunks1 = irag_index.chunk_memory("mem-hash", text, fm)
        chunks2 = irag_index.chunk_memory("mem-hash", text, fm)
        for (c1, _, _, h1), (c2, _, _, h2) in zip(chunks1, chunks2):
            self.assertEqual(h1, h2)

    def test_chunk_prefix_includes_title_type_tags(self):
        """Chunk prefix should include title, type, tags."""
        fm = _make_fm("mem-prefix", tags=["alpha", "beta"])
        text = _make_memory("mem-prefix", "My Title", "Body text.")
        chunks = irag_index.chunk_memory("mem-prefix", text, fm)
        chunk_text = chunks[0][2]
        self.assertIn("My Title", chunk_text)
        self.assertIn("type: knowledge", chunk_text)
        self.assertIn("alpha", chunk_text)
        self.assertIn("beta", chunk_text)

    def test_overlong_section_split(self):
        """A single section longer than target_chars should be split into multiple pieces."""
        long_body = "## Big Section\n\n" + "X " * 1500  # ~3000 chars
        fm = _make_fm("mem-big")
        text = _make_memory("mem-big", "Big", long_body)
        chunks = irag_index.chunk_memory("mem-big", text, fm,
                                          {"enabled": True, "threshold_chars": 200,
                                           "target_chars": 500, "overlap_chars": 50})
        self.assertGreater(len(chunks), 1)
        # The big-section slug should appear in at least one chunk
        section_slugs = [c[1] for c in chunks]
        self.assertIn("big-section", section_slugs)

    def test_no_sections_fallback_single_chunk(self):
        """Memory with no headings (just body) should still chunk."""
        fm = _make_fm("mem-nosec")
        text = _make_memory("mem-nosec", "No Sections", "Just some plain text without headings.")
        chunks = irag_index.chunk_memory("mem-nosec", text, fm)
        self.assertEqual(len(chunks), 1)


class TestChunkLevelRetrieval(unittest.TestCase):

    def _search(self, query: str, limit: int = 10) -> List[Tuple[float, Path, Dict[str, Any], str]]:
        cfg = {"retrieval": {"limit": limit, "mmr_lambda": 1.0, "min_score": 0.0,
                              "mode": "sparse", "embeddings": "off",
                              "rrf_k": 60, "sparse_weight": 1.0, "dense_weight": 1.0,
                              "candidate_multiplier": 4,
                              "chunking": {"enabled": True, "threshold_chars": 2000,
                                           "target_chars": 1200, "overlap_chars": 120}}}
        cands = []
        for p in sorted(FIXTURES_DIR.rglob("*.md")):
            text = p.read_text(encoding="utf-8")
            fm = irag.parse_fm(text)
            cands.append((p, text, fm))
        original_root = irag.ROOT
        original_rag = irag.RAG
        irag.ROOT = FIXTURES_DIR.parent
        irag.RAG = FIXTURES_DIR
        try:
            results = irag._search_with_cfg(query, limit, cfg)
        finally:
            irag.ROOT = original_root
            irag.RAG = original_rag
        return results

    def _ids(self, results) -> List[str]:
        return [fm.get("id", "") for _, _, fm, _ in results]

    def test_top_k_no_duplicate_parent(self):
        """Top-k results should not contain the same parent memory twice."""
        results = self._search("database postgres cache auth docker", limit=10)
        ids = self._ids(results)
        self.assertEqual(len(ids), len(set(ids)), f"Duplicate parent in top-k: {ids}")

    def test_five_chunks_one_doc_not_displace_five_memories(self):
        """5 chunks of one document should not displace 5 different relevant memories."""
        # Search for something that matches multiple different memories
        results = self._search("auth database cache docker test", limit=10)
        ids = self._ids(results)
        unique = set(ids)
        # We should have multiple unique memories, not all from one
        self.assertGreater(len(unique), 1, "All results from same memory — chunking not merging properly")

    def test_long_memory_info_found(self):
        """Information in a long memory should be found via chunked retrieval."""
        # Create a long memory fixture in a temp dir
        tmp = Path(tempfile.mkdtemp(prefix="irag-chunk-test-"))
        rag_dir = tmp / "INTERNAL_RAG" / "knowledge"
        rag_dir.mkdir(parents=True)
        # Create a memory where the key info is after 3000 chars
        long_body = "## Background\n\n" + "Background filler. " * 200 + "\n\n## Key Finding\n\nThe secret_token_handler function is the critical component for security.\n"
        mem_text = (
            "---\nid: mem-long-info\ntype: knowledge\nstatus: active\n"
            "created: 2024-06-01\ntags:\n  - security\ntags: []\nscope: []\n---\n\n"
            f"# Long Memory with Hidden Info\n\n## Knowledge\n\n{long_body}\n\n## Consequence\n\nNone.\n"
        )
        (rag_dir / "long-info.md").write_text(mem_text, encoding="utf-8")
        try:
            cfg = {"retrieval": {"limit": 5, "mmr_lambda": 1.0, "min_score": 0.0,
                                  "mode": "sparse", "embeddings": "off",
                                  "rrf_k": 60, "sparse_weight": 1.0, "dense_weight": 1.0,
                                  "candidate_multiplier": 4,
                                  "chunking": {"enabled": True, "threshold_chars": 500,
                                               "target_chars": 400, "overlap_chars": 50}}}
            cands = []
            for p in sorted((tmp / "INTERNAL_RAG").rglob("*.md")):
                text = p.read_text(encoding="utf-8")
                fm = irag.parse_fm(text)
                cands.append((p, text, fm))
            original_root = irag.ROOT
            original_rag = irag.RAG
            irag.ROOT = tmp
            irag.RAG = tmp / "INTERNAL_RAG"
            try:
                results = irag._search_with_cfg("secret_token_handler", 5, cfg)
                ids = self._ids(results)
                self.assertIn("mem-long-info", ids, "Info after 3000 chars not found via chunking")
            finally:
                irag.ROOT = original_root
                irag.RAG = original_rag
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_section_change_only_reembeds_that_chunk(self):
        """Changing one section should not invalidate other chunks' content hashes."""
        fm = _make_fm("mem-sections", tags=["test"])
        body = "## Section A\n\nContent A\n\n## Section B\n\nContent B\n\n## Section C\n\nContent C"
        text = _make_memory("mem-sections", "Sections", body)
        chunks1 = irag_index.chunk_memory("mem-sections", text, fm,
                                           {"enabled": True, "threshold_chars": 100,
                                            "target_chars": 1200, "overlap_chars": 120})
        # Change only section B
        body2 = "## Section A\n\nContent A\n\n## Section B\n\nContent B MODIFIED\n\n## Section C\n\nContent C"
        text2 = _make_memory("mem-sections", "Sections", body2)
        chunks2 = irag_index.chunk_memory("mem-sections", text2, fm,
                                           {"enabled": True, "threshold_chars": 100,
                                            "target_chars": 1200, "overlap_chars": 120})
        # Map by chunk_id
        hash1 = {c[0]: c[3] for c in chunks1}
        hash2 = {c[0]: c[3] for c in chunks2}
        # Sections A and C should have same hash
        a_ids = [c[0] for c in chunks1 if "section-a" in c[0]]
        c_ids = [c[0] for c in chunks1 if "section-c" in c[0]]
        b_ids = [c[0] for c in chunks1 if "section-b" in c[0]]
        if a_ids and a_ids[0] in hash2:
            self.assertEqual(hash1[a_ids[0]], hash2[a_ids[0]], "Section A hash changed unnecessarily")
        if c_ids and c_ids[0] in hash2:
            self.assertEqual(hash1[c_ids[0]], hash2[c_ids[0]], "Section C hash changed unnecessarily")
        # Section B should have different hash
        if b_ids and b_ids[0] in hash2:
            self.assertNotEqual(hash1[b_ids[0]], hash2[b_ids[0]], "Section B hash should have changed")


class TestExplainChunkFields(unittest.TestCase):

    def test_explain_has_chunk_fields(self):
        """--explain should include chunk_id, section, parent_memory_id."""
        cfg = {"retrieval": {"limit": 5, "mmr_lambda": 1.0, "min_score": 0.0,
                              "mode": "sparse", "embeddings": "off",
                              "rrf_k": 60, "sparse_weight": 1.0, "dense_weight": 1.0,
                              "candidate_multiplier": 4,
                              "chunking": {"enabled": True, "threshold_chars": 2000,
                                           "target_chars": 1200, "overlap_chars": 120}}}
        cands = []
        for p in sorted(FIXTURES_DIR.rglob("*.md")):
            text = p.read_text(encoding="utf-8")
            fm = irag.parse_fm(text)
            cands.append((p, text, fm))
        original_root = irag.ROOT
        original_rag = irag.RAG
        irag.ROOT = FIXTURES_DIR.parent
        irag.RAG = FIXTURES_DIR
        try:
            results = irag._search_with_cfg("postgres", 5, cfg, explain=True)
            self.assertTrue(len(results) > 0)
            for _, _, fm, _ in results:
                expl = fm.get("_explain")
                self.assertIsNotNone(expl)
                self.assertIn("chunk_id", expl)
                self.assertIn("section", expl)
                self.assertIn("parent_memory_id", expl)
        finally:
            irag.ROOT = original_root
            irag.RAG = original_rag


if __name__ == "__main__":
    unittest.main()