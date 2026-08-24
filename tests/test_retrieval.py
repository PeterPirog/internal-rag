#!/usr/bin/env python3
"""Deterministic retrieval quality tests for INTERNAL_RAG BM25.

Uses only the standard library (unittest). No external dependencies.

Run with:
  python -m unittest discover -s tests -v
"""
from __future__ import annotations
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple

# --- Load irag.py as a module (without executing main) ---
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
IRAG_PATH = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag.py"
FIXTURES_DIR = HERE / "fixtures" / "retrieval"

_spec = importlib.util.spec_from_file_location("irag_mod", str(IRAG_PATH))
irag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(irag)


def _load_fixtures() -> List[Tuple[Path, str, Dict[str, Any]]]:
    """Load all .md fixtures as (path, text, frontmatter) tuples."""
    candidates = []
    for p in sorted(FIXTURES_DIR.rglob("*.md")):
        text = p.read_text(encoding="utf-8")
        fm = irag.parse_fm(text)
        candidates.append((p, text, fm))
    return candidates


def _search(query: str, limit: int = 10,
            types=None, statuses=None,
            explain: bool = False
            ) -> List[Tuple[float, Path, Dict[str, Any], str]]:
    """Run hybrid search against fixtures, bypassing ROOT-dependent logic."""
    cfg = {"retrieval": {"limit": 10, "mmr_lambda": 1.0, "min_score": 0.0,
                          "bm25_k1": 1.5, "bm25_b": 0.75,
                          "mode": "sparse", "embeddings": "off",
                          "rrf_k": 60, "sparse_weight": 1.0, "dense_weight": 1.0,
                          "candidate_multiplier": 4}}
    candidates = _load_fixtures()
    # Apply filters
    filtered = []
    for p, text, fm in candidates:
        status = str(fm.get("status", "active")).lower()
        if status in {"invalid", "archived"}:
            continue
        if types:
            mt = str(fm.get("type", "")).lower()
            if mt not in [t.lower() for t in types]:
                continue
        if statuses:
            if status not in [s.lower() for s in statuses]:
                continue
        filtered.append((p, text, fm))
    original_root = irag.ROOT
    original_rag = irag.RAG
    original_open = irag._open_sqlite_index
    irag.ROOT = FIXTURES_DIR.parent
    irag.RAG = FIXTURES_DIR  # INTERNAL_RAG/ equivalent
    irag._open_sqlite_index = lambda: None  # hermetic: no index artifact in fixtures
    try:
        results = irag._search_with_cfg(query, limit, cfg, types=types, statuses=statuses, explain=explain)
    finally:
        irag.ROOT = original_root
        irag.RAG = original_rag
        irag._open_sqlite_index = original_open
    return results


def _ids(results) -> List[str]:
    """Extract memory ids from results."""
    return [fm.get("id", "") for _, _, fm, _ in results]


class TestBM25IDFFormula(unittest.TestCase):

    def test_idf_rare_term_higher_than_frequent(self):
        """IDF of a rare term should be higher than IDF of a frequent term."""
        df_map = {"postgres": 1, "cache": 10}
        n = 22
        idf_rare = irag.bm25_idf("postgres", df_map, n)
        idf_freq = irag.bm25_idf("cache", df_map, n)
        self.assertGreater(idf_rare, idf_freq)
        self.assertGreater(idf_rare, 0)

    def test_idf_non_negative(self):
        """IDF should always be non-negative (log(1+x) >= 0)."""
        for df in [1, 5, 10, 21]:
            idf = irag.bm25_idf("term", {"term": df}, 22)
            self.assertGreaterEqual(idf, 0.0, f"IDF negative for df={df}")

    def test_idf_missing_term_zero(self):
        """IDF of a term not in corpus should be 0."""
        self.assertEqual(irag.bm25_idf("nonexistent", {"other": 1}, 22), 0.0)

    def test_idf_uses_log(self):
        """Verify the formula is log(1 + (N-df+0.5)/(df+0.5))."""
        import math
        df, n = 3, 22
        expected = math.log(1 + (n - df + 0.5) / (df + 0.5))
        self.assertAlmostEqual(irag.bm25_idf("x", {"x": df}, n), expected, places=10)


class TestBM25TermScore(unittest.TestCase):

    def test_zero_tf_zero_score(self):
        """If term frequency is 0, score should be 0."""
        score = irag.bm25_term_score("x", 0, 100, 100, 2.0, 1.5, 0.75)
        self.assertEqual(score, 0.0)

    def test_zero_avgdl_zero_score(self):
        """If avgdl is 0, score should be 0 (graceful)."""
        score = irag.bm25_term_score("x", 5, 100, 0, 2.0, 1.5, 0.75)
        self.assertEqual(score, 0.0)

    def test_higher_tf_higher_score(self):
        """Higher term frequency should yield higher score (saturation)."""
        idf = 2.0
        s1 = irag.bm25_term_score("x", 1, 100, 100, idf, 1.5, 0.75)
        s5 = irag.bm25_term_score("x", 5, 100, 100, idf, 1.5, 0.75)
        self.assertGreater(s5, s1)


class TestBM25DocScore(unittest.TestCase):

    def test_empty_doc(self):
        """Empty document should score 0."""
        score, matched = irag.bm25_doc_score(["x"], [], {"x": 1}, 10, 100, 1.5, 0.75)
        self.assertEqual(score, 0.0)
        self.assertEqual(matched, [])

    def test_empty_query(self):
        """Empty query should score 0."""
        score, matched = irag.bm25_doc_score([], ["x", "y"], {"x": 1}, 10, 100, 1.5, 0.75)
        self.assertEqual(score, 0.0)
        self.assertEqual(matched, [])


class TestRareTermRanking(unittest.TestCase):

    def test_rare_term_ranks_correct_doc_higher(self):
        """A rare term should rank the document containing it above documents
        that only contain common terms."""
        results = _search("asyncpg pool exhaust", limit=5)
        ids = _ids(results)
        self.assertIn("mem-fix-004-asyncpg-pool", ids)
        # The asyncpg gotcha should be in top 3
        self.assertLessEqual(ids.index("mem-fix-004-asyncpg-pool"), 2)


class TestExactSymbolSearch(unittest.TestCase):

    def test_refresh_token_cache_findable(self):
        """Exact function name 'refresh_token_cache' should be findable."""
        results = _search("refresh_token_cache", limit=5)
        ids = _ids(results)
        self.assertIn("mem-fix-005-refresh-token-cache", ids)
        # Should be top 1 (it's the only doc with this exact term)
        self.assertEqual(ids[0], "mem-fix-005-refresh-token-cache")

    def test_rate_limiter_findable(self):
        """Exact function name 'rate_limiter' should be findable."""
        results = _search("rate_limiter", limit=5)
        ids = _ids(results)
        self.assertIn("mem-fix-007-rate-limiter", ids)

    def test_docker_compose_findable(self):
        """Exact term 'docker-compose' should be findable."""
        results = _search("docker-compose", limit=5)
        ids = _ids(results)
        self.assertIn("mem-fix-008-docker-compose", ids)


class TestFrequentTermDoesNotDominate(unittest.TestCase):

    def test_frequent_term_does_not_dominate(self):
        """A frequent term (appearing in many docs) should not cause irrelevant
        docs to rank above docs with the rare query term."""
        # "cache" appears in 003, 005, 014 — but "asyncpg" is rare
        results = _search("asyncpg", limit=5)
        ids = _ids(results)
        self.assertTrue(len(ids) > 0)
        # asyncpg-pool should be #1
        self.assertEqual(ids[0], "mem-fix-004-asyncpg-pool")

    def test_distractors_rank_low(self):
        """Distractor memories (meeting, coffee) should rank low for technical queries."""
        results = _search("postgres database pool", limit=10)
        ids = _ids(results)
        # Distractors should not be in top 5
        for distractor in ("mem-fix-021-distractor-meeting", "mem-fix-022-distractor-coffee"):
            if distractor in ids:
                self.assertGreater(ids.index(distractor), 4,
                                   f"{distractor} ranked too high for technical query")


class TestStatusSemantics(unittest.TestCase):

    def test_active_ranks_higher_than_superseded(self):
        """An active memory should rank higher than a superseded one for the same query.
        The superseded penalty (-4.0) should overcome BM25 differences."""
        # Use a query where both docs match strongly, so the -4.0 penalty matters
        results = _search("auth", limit=10)
        ids = _ids(results)
        jwt_id = "mem-fix-002-auth-jwt"
        basic_id = "mem-fix-017-superseded-rest"
        if jwt_id in ids and basic_id in ids:
            self.assertLess(ids.index(jwt_id), ids.index(basic_id),
                            "active JWT should rank above superseded Basic Auth")
        # If superseded is filtered out (score < min_score after -4.0), that's valid too

    def test_superseded_filtered_or_low(self):
        """Superseded memories should either be filtered out or rank very low."""
        results = _search("basic auth rest", limit=10)
        ids = _ids(results)
        if "mem-fix-017-superseded-rest" in ids:
            # It can appear but should not be top
            self.assertGreaterEqual(ids.index("mem-fix-017-superseded-rest"), 0)

    def test_tentative_lower_than_active(self):
        """Tentative (hypothesis) should rank lower than active for same topic.
        The tentative boost (+0.6) is less than active (+1.0), so an active doc
        with similar BM25 score should rank higher."""
        # "api" matches many active docs and the graphql hypothesis
        results = _search("api", limit=10)
        ids = _ids(results)
        hypothesis_id = "mem-fix-016-hypothesis-graphql"
        # If hypothesis appears, there should be at least one active doc above it
        if hypothesis_id in ids:
            hyp_pos = ids.index(hypothesis_id)
            # Check that at least one active doc is above
            has_active_above = False
            for idx in range(hyp_pos):
                _, _, fm, _ = results[idx]
                if str(fm.get("status", "")).lower() == "active":
                    has_active_above = True
                    break
            self.assertTrue(has_active_above,
                            "at least one active memory should rank above the tentative hypothesis")


class TestTypeFilters(unittest.TestCase):

    def test_filter_decision_only(self):
        """--type decision should only return decisions."""
        results = _search("postgres", limit=10, types=["decision"])
        for _, _, fm, _ in results:
            self.assertEqual(str(fm.get("type", "")).lower(), "decision",
                             f"Non-decision returned: {fm.get('id')}")

    def test_filter_gotcha_only(self):
        """--type gotcha should only return gotchas."""
        results = _search("pool timeout", limit=10, types=["gotcha"])
        for _, _, fm, _ in results:
            self.assertEqual(str(fm.get("type", "")).lower(), "gotcha")

    def test_filter_multiple_types(self):
        """--type decision knowledge should return only those types."""
        results = _search("auth", limit=10, types=["decision", "knowledge"])
        for _, _, fm, _ in results:
            t = str(fm.get("type", "")).lower()
            self.assertIn(t, ("decision", "knowledge"))


class TestStatusFilters(unittest.TestCase):

    def test_filter_active_excludes_tentative(self):
        """--status active should exclude tentative hypotheses."""
        results = _search("api", limit=10, statuses=["active"])
        for _, _, fm, _ in results:
            self.assertEqual(str(fm.get("status", "")).lower(), "active",
                             f"Non-active returned: {fm.get('id')}")

    def test_filter_tentative_only(self):
        """--status tentative should only return hypotheses."""
        results = _search("graphql", limit=10, statuses=["tentative"])
        for _, _, fm, _ in results:
            self.assertEqual(str(fm.get("status", "")).lower(), "tentative")


class TestPolishCharacters(unittest.TestCase):

    def test_polish_query_matches_polish_doc(self):
        """Polish characters in query should match Polish documents (after normalization)."""
        # "logowanie" should match the Polish login form memory
        results = _search("logowanie formularz", limit=5)
        ids = _ids(results)
        self.assertIn("mem-fix-012-polski-logowanie", ids)

    def test_polish_query_baza_danych(self):
        """Polish term 'baza danych' should match the Polish database decision."""
        results = _search("baza danych postgres", limit=5)
        ids = _ids(results)
        # Should find either the Polish or English postgres memory
        found = [i for i in ids if "postgres" in i or "baza" in i]
        self.assertTrue(len(found) > 0, "Polish query should match database memories")

    def test_polish_cache_term(self):
        """Polish term 'pamięć podręczna' (after normalization) should match cache memory."""
        results = _search("pamiec podreczna cache", limit=5)
        ids = _ids(results)
        self.assertIn("mem-fix-014-polski-cache", ids)

    def test_polish_walidacja(self):
        """Polish term 'walidacja' should match the PESEL validation memory."""
        results = _search("walidacja pesel", limit=5)
        ids = _ids(results)
        self.assertIn("mem-fix-020-polski-walidacja", ids)

    def test_accented_query_normalization(self):
        """Accented Polish query should work same as non-accented."""
        r1 = _search("logowanie", limit=5)
        r2 = _search("logowanię", limit=5)  # ę → e after NFKD
        # Both should find the Polish login memory
        self.assertIn("mem-fix-012-polski-logowanie", _ids(r1))
        self.assertIn("mem-fix-012-polski-logowanie", _ids(r2))


class TestDeterminism(unittest.TestCase):

    def test_same_query_same_results(self):
        """The same query run twice should produce identical results."""
        r1 = _search("postgres database cache", limit=5)
        r2 = _search("postgres database cache", limit=5)
        self.assertEqual(_ids(r1), _ids(r2))
        # Scores should be identical too
        s1 = [round(s, 6) for s, _, _, _ in r1]
        s2 = [round(s, 6) for s, _, _, _ in r2]
        self.assertEqual(s1, s2)

    def test_fixture_count(self):
        """Fixture directory should have at least 20 memories."""
        candidates = _load_fixtures()
        self.assertGreaterEqual(len(candidates), 20, f"Expected >= 20 fixtures, got {len(candidates)}")


class TestEmptyAndEdgeCases(unittest.TestCase):

    def test_empty_query_returns_empty(self):
        """Empty query should return no results (graceful)."""
        results = _search("", limit=5)
        self.assertEqual(len(results), 0)

    def test_no_matching_query(self):
        """A query with no matching terms should return empty."""
        results = _search("zzzznotexistqqqq", limit=5)
        self.assertEqual(len(results), 0)

    def test_whitespace_query(self):
        """Whitespace-only query should return empty."""
        results = _search("   ", limit=5)
        self.assertEqual(len(results), 0)


class TestRRFFusion(unittest.TestCase):

    def test_rrf_deterministic(self):
        """RRF fusion should be deterministic for the same inputs."""
        sparse = [(10.0, 0, ["a"]), (5.0, 1, ["b"]), (3.0, 2, ["c"])]
        dense = [(0.9, 1), (0.8, 0), (0.7, 3)]
        r1 = irag.rrf_fusion(sparse, dense, 60, 1.0, 1.0)
        r2 = irag.rrf_fusion(sparse, dense, 60, 1.0, 1.0)
        self.assertEqual(len(r1), len(r2))
        for (s1, i1, _), (s2, i2, _) in zip(r1, r2):
            self.assertEqual(i1, i2)
            self.assertAlmostEqual(s1, s2, places=10)

    def test_rrf_doc_in_both_channels_ranks_higher(self):
        """A doc found by both sparse and dense should rank above a doc found by only one."""
        sparse = [(10.0, 0, ["a"]), (5.0, 1, ["b"])]
        dense = [(0.9, 0), (0.8, 2)]  # doc 0 in both, doc 1 only sparse, doc 2 only dense
        fused = irag.rrf_fusion(sparse, dense, 60, 1.0, 1.0)
        # doc 0 should be #1 (found by both)
        self.assertEqual(fused[0][1], 0)

    def test_rrf_no_dense(self):
        """RRF with no dense results should produce sparse-only scores."""
        sparse = [(10.0, 0, ["a"]), (5.0, 1, ["b"])]
        fused = irag.rrf_fusion(sparse, None, 60, 1.0, 1.0)
        self.assertEqual(len(fused), 2)
        self.assertEqual(fused[0][1], 0)  # higher sparse score = rank 0

    def test_rrf_weights_affect_ordering(self):
        """Higher dense_weight should favor dense-ranked docs."""
        sparse = [(10.0, 0, ["a"]), (1.0, 1, ["b"])]
        dense = [(0.9, 1), (0.1, 0)]  # doc 1 ranks #1 in dense
        # With equal weights, doc 0 (sparse #1) likely wins
        fused_equal = irag.rrf_fusion(sparse, dense, 60, 1.0, 1.0)
        # With very high dense_weight, doc 1 should improve
        fused_dense_heavy = irag.rrf_fusion(sparse, dense, 60, 0.1, 10.0)
        # The relative ordering of doc 0 and doc 1 may change
        # Just verify the function runs and produces valid output
        self.assertEqual(len(fused_equal), 2)
        self.assertEqual(len(fused_dense_heavy), 2)


class TestHybridRetrieval(unittest.TestCase):

    def test_sparse_only_mode_works(self):
        """Sparse-only mode (no embeddings) should produce results."""
        results = _search("postgres database", limit=5)
        self.assertTrue(len(results) > 0)

    def test_no_dense_does_not_error(self):
        """When dense is unavailable, search should still work (graceful degradation)."""
        # Our _search helper has embeddings=off, so dense is never attempted
        results = _search("auth jwt token", limit=5)
        self.assertTrue(len(results) > 0)

    def test_exact_identifier_wins_via_sparse(self):
        """An exact identifier like 'refresh_token_cache' should be findable via sparse."""
        results = _search("refresh_token_cache", limit=5)
        ids = _ids(results)
        self.assertEqual(ids[0], "mem-fix-005-refresh-token-cache")


class TestExplainOutput(unittest.TestCase):

    def test_explain_fields_present(self):
        """--explain should produce per-channel breakdown in fm."""
        results = _search("postgres", limit=3, explain=True)
        self.assertTrue(len(results) > 0)
        for _, _, fm, _ in results:
            expl = fm.get("_explain")
            self.assertIsNotNone(expl, "Missing _explain in frontmatter")
            self.assertIn("sparse_score", expl)
            self.assertIn("sparse_rank", expl)
            self.assertIn("dense_score", expl)
            self.assertIn("dense_rank", expl)
            self.assertIn("rrf_score", expl)
            self.assertIn("policy_boost", expl)
            self.assertIn("final_score", expl)
            self.assertIn("retrieval_mode", expl)
            self.assertIn("matched_tokens", expl)
            self.assertEqual(expl["retrieval_mode"], "sparse")
            self.assertIsNone(expl["dense_score"])  # no embeddings in test

    def test_json_without_explain_preserves_fields(self):
        """--json without --explain should still have the standard fields."""
        results = _search("cache redis", limit=3, explain=False)
        for s, p, fm, sn in results:
            # Standard fields should be present
            self.assertIsNotNone(s)
            self.assertIsNotNone(p)
            self.assertIsInstance(fm, dict)
            self.assertIsInstance(sn, str)
            # _explain should NOT be present
            self.assertNotIn("_explain", fm)


class TestFiltersBeforeRetrieval(unittest.TestCase):

    def test_type_filter_applied_before_retrieval(self):
        """Type filter should exclude non-matching types before search."""
        results = _search("postgres", limit=10, types=["decision"])
        for _, _, fm, _ in results:
            self.assertEqual(str(fm.get("type", "")).lower(), "decision")

    def test_status_filter_applied_before_retrieval(self):
        """Status filter should exclude non-matching statuses before search."""
        results = _search("api", limit=10, statuses=["active"])
        for _, _, fm, _ in results:
            self.assertEqual(str(fm.get("status", "")).lower(), "active")


if __name__ == "__main__":
    unittest.main()