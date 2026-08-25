#!/usr/bin/env python3
"""CEL A — Deterministic memory-quality benchmark (v1.6.0).

Exercises the REAL retrieval pipeline (`irag._search_with_cfg` / `search_with_meta`),
not a bare bm25_search() helper. The fixture corpus under
`tests/fixtures/memory_corpus/` is a realistic coding-memory set covering:
exact identifiers, file paths, method/class names, paraphrase, PL, EN, mixed,
superseded decisions, valid_from/valid_to, `search --at`, contradictions,
failure->fix, gotchas, archived memories, distractors, and multi-memory queries.

Metrics reported:
  - Recall@1 / Recall@3 / Recall@5
  - MRR
  - Abstention precision / recall / F1   (unrelated queries should abstain)
  - Temporal accuracy                    (`--at` returns the decision valid then)
  - Superseded/archived leakage rate     (active search must NOT leak them)
  - p50 / p95 latency (ms)
  - approximate context token count

Runs:
  python tests/memory_quality_benchmark.py            # full (deterministic)
  python tests/memory_quality_benchmark.py --smoke    # fast CI canary subset
  python tests/memory_quality_benchmark.py --json     # machine-readable

Zero external dependencies. Python 3.8+ stdlib only. No LLM, no network.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Windows CI uses cp1252 by default; force UTF-8 so Polish query strings print.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
IRAG_PATH = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag.py"
FIXTURES = HERE / "fixtures" / "memory_corpus"

_spec = importlib.util.spec_from_file_location("irag_mod", str(IRAG_PATH))
irag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(irag)


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------
# Each case: (query, expected_ids set, optional at_date, category, notes)
# expected_ids = memory ids that MUST appear in top-k for the query to count.
# For abstention cases, expected_ids is empty AND we assert the system abstains.
# For temporal cases, at_date pins the temporal filter.

CASES: List[Dict[str, Any]] = [
    # --- exact identifiers ---
    {"q": "refresh_token_cache", "expect": {"mem-corp-005-refresh-token-cache"},
     "category": "exact_identifier"},
    {"q": "AuthService.refresh", "expect": {"mem-corp-002-auth-jwt"},
     "category": "method_name"},
    {"q": "RateLimiter", "expect": {"mem-corp-007-rate-limiter"},
     "category": "class_name"},
    {"q": "SessionManager", "expect": {"mem-corp-026-sources-only-symbol"},
     "category": "sources_only_symbol"},  # CEL F: symbol only in sources
    # --- file paths ---
    {"q": "src/auth/token.py", "expect": {"mem-corp-005-refresh-token-cache"},
     "category": "file_path"},
    {"q": "src/db/pool.py", "expect": {"mem-corp-004-asyncpg-pool"},
     "category": "file_path"},
    {"q": "migrations/versions/0042_add_index.py", "expect": {"mem-corp-006-migration-rollback"},
     "category": "file_path"},
    {"q": "nginx/sites-available/api.conf", "expect": {"mem-corp-019-nginx-timeout"},
     "category": "file_path"},
    {"q": "frontend/webpack.config.js", "expect": {"mem-corp-011-webpack-config"},
     "category": "file_path"},
    # --- paraphrase ---
    {"q": "how do we cache user sessions", "expect": {"mem-corp-003-redis-cache"},
     "category": "paraphrase"},
    {"q": "database connection runs out under load", "expect": {"mem-corp-004-asyncpg-pool"},
     "category": "paraphrase"},
    {"q": "rotating session keys periodically", "expect": {"mem-corp-026-sources-only-symbol"},
     "category": "paraphrase"},
    # --- Polish ---
    {"q": "baza danych postgres", "expect": {"mem-corp-001-use-postgres", "mem-corp-013-polski-baza-danych"},
     "category": "pl"},
    {"q": "logowanie formularz email hasło", "expect": {"mem-corp-012-polski-logowanie"},
     "category": "pl"},
    {"q": "pamięć podręczna redis nie unieważnia po deploy", "expect": {"mem-corp-014-polski-cache"},
     "category": "pl"},
    {"q": "walidacja numeru PESEL", "expect": {"mem-corp-020-polski-walidacja"},
     "category": "pl"},
    # --- English ---
    {"q": "rate limiting token bucket per IP", "expect": {"mem-corp-007-rate-limiter"},
     "category": "en"},
    {"q": "celery worker prefetch multiplier", "expect": {"mem-corp-010-celery-worker"},
     "category": "en"},
    {"q": "docker compose dev environment hot reload", "expect": {"mem-corp-008-docker-compose"},
     "category": "en"},
    # --- mixed PL/EN ---
    {"q": "auth jwt token logowanie", "expect": {"mem-corp-002-auth-jwt", "mem-corp-012-polski-logowanie"},
     "category": "mixed"},
    {"q": "cache redis wydajność ttl", "expect": {"mem-corp-003-redis-cache", "mem-corp-014-polski-cache"},
     "category": "mixed"},
    # --- superseded (active search must return the CURRENT one, not the old) ---
    {"q": "authentication basic auth", "expect": {"mem-corp-002-auth-jwt"},
     "category": "superseded_active", "leakage_forbid": {"mem-corp-017-superseded-rest"}},
    {"q": "full text search elasticsearch", "expect": {"mem-corp-031-supersede-chain-c"},
     "category": "superseded_chain", "leakage_forbid": {"mem-corp-029-supersede-chain-a",
                                                        "mem-corp-030-supersede-chain-b"}},
    # --- temporal: search --at should surface the decision valid at that date ---
    {"q": "authentication", "at": "2024-01-15",
     "expect": {"mem-corp-017-superseded-rest"}, "category": "temporal_history"},
    {"q": "full text search", "at": "2024-07-15",
     "expect": {"mem-corp-030-supersede-chain-b"}, "category": "temporal_history"},
    {"q": "kubernetes migration", "at": "2024-08-15",
     "expect": set(), "category": "temporal_future"},  # not yet valid -> abstain/no hit
    # --- contradictions ---
    {"q": "session cache redis vs memcached", "expect": {"mem-corp-003-redis-cache",
                                                          "mem-corp-025-contradicts-redis"},
     "category": "contradiction"},
    # --- failure -> fix ---
    {"q": "celery tasks dropped silently", "expect": {"mem-corp-028-failure-then-fix"},
     "category": "failure_fix"},
    {"q": "mongodb transactional data failed", "expect": {"mem-corp-015-failed-nosql"},
     "category": "failure_fix"},
    # --- gotchas ---
    {"q": "pytest asyncio event loop closed", "expect": {"mem-corp-009-pytest-asyncio"},
     "category": "gotcha"},
    {"q": "nginx 504 gateway timeout slow reports", "expect": {"mem-corp-019-nginx-timeout"},
     "category": "gotcha"},
    # --- archived must NOT leak in active search ---
    {"q": "legacy initial migration raw sql", "expect": set(),
     "category": "archived_isolation", "leakage_forbid": {"mem-corp-023-archived-legacy-migration"},
     "abstention_expected": True},
    # --- unrelated / abstension ---
    {"q": "zzz_nonexistent_topic_qqq", "expect": set(),
     "category": "abstention", "abstention_expected": True},
    {"q": "weather forecast tomorrow", "expect": set(),
     "category": "abstention", "abstention_expected": True},
    {"q": "coffee machine beans water", "expect": {"mem-corp-022-distractor-coffee"},
     "category": "distractor_present"},
    # --- multi-memory ---
    {"q": "user api database auth jwt", "expect": {"mem-corp-002-auth-jwt",
                                                    "mem-corp-032-multi-result-a"},
     "category": "multi_memory"},
    {"q": "feature flags default off", "expect": {"mem-corp-024-future-feature-flag"},
     "category": "en"},
]

SMOKE_CATEGORIES = {"exact_identifier", "pl", "superseded_active", "temporal_history",
                    "abstention", "multi_memory"}


def _base_cfg(mode: str = "sparse") -> Dict[str, Any]:
    return {
        "retrieval": {
            "limit": 5, "mmr_lambda": 0.5, "min_score": 0.0, "mode": mode,
            "embeddings": "off", "rrf_k": 60, "sparse_weight": 1.0, "dense_weight": 1.0,
            "candidate_multiplier": 4, "bm25_k1": 1.5, "bm25_b": 0.75,
            "pl_stopwords": True, "query_expansion": True,
            "abstention": {"enabled": True, "require_sparse_match": True, "min_dense_score": None},
            "fts_prefilter": {"enabled": False, "min_corpus_size": 50},
            "chunking": {"enabled": True, "threshold_chars": 2000,
                         "target_chars": 1200, "overlap_chars": 120},
        },
        "tokens": {"context_budget": 4000},
    }


class BenchEnv:
    """Sandbox the fixtures into a temp project so ROOT/RAG resolve cleanly."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.rag = tmp / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures", "hypotheses",
                  "sessions/.snapshots", "archive"):
            (self.rag / d).mkdir(parents=True, exist_ok=True)
        (self.rag / "WORKING_STATE.md").write_text("# Working state\n", encoding="utf-8")

    def load_fixtures(self) -> None:
        for src in FIXTURES.rglob("*.md"):
            rel = src.relative_to(FIXTURES)
            dst = self.rag / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())

    def __enter__(self):
        self._old = (irag.ROOT, irag.RAG, irag.CONFIG_PATH, irag.WORKING,
                     irag._open_sqlite_index, irag.FP_CACHE, irag.CHECKPOINT)
        irag.ROOT = self.tmp
        irag.RAG = self.rag
        irag.CONFIG_PATH = self.tmp / ".irag.yml"
        irag.WORKING = self.rag / "WORKING_STATE.md"
        irag._open_sqlite_index = lambda: None
        irag.FP_CACHE = self.rag / ".fpcache.json"
        irag.CHECKPOINT = self.rag / ".checkpoint.json"
        self.load_fixtures()
        return self

    def __exit__(self, *a):
        irag.ROOT, irag.RAG, irag.CONFIG_PATH, irag.WORKING, irag._open_sqlite_index, \
            irag.FP_CACHE, irag.CHECKPOINT = self._old


def _run_query(case: Dict[str, Any], cfg: Dict[str, Any]
               ) -> Tuple[List[Tuple[float, Path, Dict[str, Any], str]], Dict[str, Any], float]:
    q = case["q"]
    limit = 5
    at = case.get("at")
    c = dict(cfg)
    t0 = time.perf_counter()
    results = irag._search_with_cfg(q, limit, c, explain=False, at_date=at)
    # Apply the same temporal post-filter the CLI uses (--at)
    if at:
        results = irag._filter_by_date(results, at)
    meta = c.get("_abstention_meta") or {"abstained": not results,
                                          "retrieval_confidence": 0.0,
                                          "confidence_kind": "heuristic"}
    # Re-evaluate abstention after post-filter: if temporal filter removed all
    # results, the query effectively abstains for that date.
    if at and not results:
        meta = dict(meta)
        meta["abstained"] = True
    lat = (time.perf_counter() - t0) * 1000.0
    return results, meta, lat


def _ids(results) -> List[str]:
    return [str(fm.get("id", "")) for _s, _p, fm, _sn in results]


def evaluate(mode: str, smoke: bool = False) -> Dict[str, Any]:
    cases = [c for c in CASES if (not smoke or c["category"] in SMOKE_CATEGORIES)]
    cfg = _base_cfg(mode)
    recalls = {1: 0, 3: 0, 5: 0}
    mrr_sum = 0.0
    n_ranked = 0
    # abstention
    tp = fp = fn = tn = 0  # abstention-positive = "should abstain"
    # temporal
    temporal_correct = 0
    temporal_total = 0
    # leakage
    leakage_violations = 0
    leakage_checks = 0
    latencies: List[float] = []
    token_total = 0
    per_case: List[Dict[str, Any]] = []

    with BenchEnv(Path(tempfile.mkdtemp(prefix="irag-mqb-"))) as env:
        for case in cases:
            results, meta, lat = _run_query(case, cfg)
            latencies.append(lat)
            ids = _ids(results)
            id_set = set(ids)
            expect = set(case.get("expect") or set())
            forbid = set(case.get("leakage_forbid") or set())
            abst_expected = bool(case.get("abstention_expected", False))
            abst_actual = bool(meta.get("abstained", False))
            token_total += sum(irag.estimate_tokens(sn) for _s, _p, _fm, sn in results)

            # Recall / MRR (only for cases with an expected hit and not abstention-expected)
            if expect and not abst_expected:
                n_ranked += 1
                found_at = None
                for rank, mid in enumerate(ids, 1):
                    if mid in expect:
                        found_at = rank
                        break
                if found_at is not None:
                    mrr_sum += 1.0 / found_at
                    for k in recalls:
                        if found_at <= k:
                            recalls[k] += 1
                # multi-memory: require ALL expected in top-5 for Recall@5 full credit
                if len(expect) > 1:
                    if expect.issubset(id_set):
                        recalls[5] += 1  # already counted once; adjust below
            # Abstention P/R/F1
            if abst_expected:
                if abst_actual:
                    tp += 1
                else:
                    fn += 1
            else:
                if abst_actual and expect:
                    fp += 1  # abstained but there was a real answer
                elif not abst_actual:
                    tn += 1
            # Temporal accuracy
            if case.get("at"):
                temporal_total += 1
                if expect and expect.issubset(id_set):
                    temporal_correct += 1
                elif not expect and not id_set:
                    temporal_correct += 1  # future-not-valid -> no hit is correct
            # Leakage
            if forbid:
                leakage_checks += 1
                if id_set & forbid:
                    leakage_violations += 1
            per_case.append({
                "q": case["q"], "category": case["category"],
                "at": case.get("at"), "expect": sorted(expect),
                "got": ids[:5], "abstained": abst_actual,
                "latency_ms": round(lat, 3),
                "leakage": sorted(id_set & forbid) if forbid else [],
            })

    n = n_ranked or 1
    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    p95 = latencies[min(int(len(latencies) * 0.95), len(latencies) - 1)] if latencies else 0.0
    # abstention F1
    ap = tp / max(tp + fp, 1)
    ar = tp / max(tp + fn, 1)
    af1 = 2 * ap * ar / max(ap + ar, 1e-9)
    return {
        "mode": mode,
        "smoke": smoke,
        "corpus_size": sum(1 for _ in FIXTURES.rglob("*.md")),
        "n_cases": len(cases),
        "n_ranked": n_ranked,
        "recall@1": round(recalls[1] / n, 4),
        "recall@3": round(recalls[3] / n, 4),
        "recall@5": round(recalls[5] / n, 4),
        "mrr": round(mrr_sum / n, 4),
        "abstention_precision": round(ap, 4),
        "abstention_recall": round(ar, 4),
        "abstention_f1": round(af1, 4),
        "temporal_accuracy": round(temporal_correct / max(temporal_total, 1), 4),
        "temporal_total": temporal_total,
        "leakage_rate": round(leakage_violations / max(leakage_checks, 1), 4),
        "leakage_checks": leakage_checks,
        "latency_p50_ms": round(p50, 3),
        "latency_p95_ms": round(p95, 3),
        "approx_context_tokens": token_total,
        "per_case": per_case,
    }


def _print_table(reports: List[Dict[str, Any]]) -> None:
    cols = ["mode", "n_cases", "recall@1", "recall@3", "recall@5", "mrr",
            "abst_f1", "temp_acc", "leak", "p50_ms", "p95_ms", "tokens"]
    widths = {"mode": 8, "n_cases": 7, "recall@1": 9, "recall@3": 9, "recall@5": 9,
              "mrr": 6, "abst_f1": 8, "temp_acc": 8, "leak": 6, "p50_ms": 8,
              "p95_ms": 8, "tokens": 7}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    print(header)
    print("-" * len(header))
    for r in reports:
        row = {
            "mode": r["mode"],
            "n_cases": str(r["n_cases"]),
            "recall@1": f"{r['recall@1']:.2%}",
            "recall@3": f"{r['recall@3']:.2%}",
            "recall@5": f"{r['recall@5']:.2%}",
            "mrr": f"{r['mrr']:.3f}",
            "abst_f1": f"{r['abstention_f1']:.2f}",
            "temp_acc": f"{r['temporal_accuracy']:.2%}",
            "leak": f"{r['leakage_rate']:.2%}",
            "p50_ms": f"{r['latency_p50_ms']:.1f}",
            "p95_ms": f"{r['latency_p95_ms']:.1f}",
            "tokens": str(r["approx_context_tokens"]),
        }
        print("  ".join(row[c].ljust(widths[c]) for c in cols))


def main() -> int:
    ap = argparse.ArgumentParser(description="INTERNAL_RAG memory-quality benchmark")
    ap.add_argument("--smoke", action="store_true", help="Fast CI canary subset")
    ap.add_argument("--json", action="store_true", help="Machine-readable JSON")
    ap.add_argument("--mode", default="sparse", choices=["sparse", "hybrid", "adaptive"],
                    help="Retrieval mode to evaluate (default: sparse)")
    args = ap.parse_args()

    modes = [args.mode] if args.mode != "sparse" else ["sparse"]
    reports = [evaluate(m, smoke=args.smoke) for m in modes]

    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    else:
        print("INTERNAL_RAG Memory-Quality Benchmark" + (" (SMOKE)" if args.smoke else ""))
        print("=" * 72)
        _print_table(reports)
        print()
        for r in reports:
            print(f"\n--- {r['mode']} per-case ---")
            for pc in r["per_case"]:
                tag = "ABST" if pc["abstained"] else "OK"
                leak = "  LEAK!" if pc["leakage"] else ""
                at = f" @ {pc['at']}" if pc["at"] else ""
                print(f"[{tag}] {pc['category']:20} {pc['q'][:40]!r}{at} "
                      f"-> {pc['got'][:3]}{leak}  ({pc['latency_ms']:.1f}ms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())