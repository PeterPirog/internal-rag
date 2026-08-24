#!/usr/bin/env python3
"""Retrieval benchmark for INTERNAL_RAG BM25.

Measures Recall@1, Recall@3, Recall@5, MRR, and latency (p50, p95)
on synthetic corpora of 100, 1000, and 10000 records.

Not part of self_test — run explicitly:
  python tests/retrieval_benchmark.py

Zero external dependencies. Uses only standard library.
"""
from __future__ import annotations
import importlib.util
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
IRAG_PATH = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag.py"

_spec = importlib.util.spec_from_file_location("irag_mod", str(IRAG_PATH))
irag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(irag)

# Patch ROOT so relative_to works in bm25_search
irag.ROOT = HERE


def _make_fm(mem_id: str, mtype: str, status: str, created: str) -> str:
    return (
        f"---\nid: {mem_id}\ntype: {mtype}\nstatus: {status}\n"
        f"created: {created}\nverified: {created}\nscope: []\ntags: []\nsources: []\nlinks: []\n---\n\n"
        f"# {mem_id}\n\n## Knowledge\n\n"
    )


def generate_corpus(n: int, seed: int = 42) -> List[Tuple[Path, str, Dict[str, Any]]]:
    """Generate a synthetic corpus of n memories with deterministic content."""
    rng = random.Random(seed)
    topics = [
        "database postgres pool connection timeout asyncpg",
        "authentication jwt token refresh oauth bearer security",
        "cache redis memory ttl invalidation eviction lru",
        "docker container kubernetes deployment orchestration helm",
        "api rest graphql endpoint rate_limit middleware cors",
        "frontend react vue webpack bundler typescript eslint",
        "test pytest unittest mock fixture coverage async",
        "migration alembic schema rollback upgrade downgrade",
        "queue celery worker rabbitmq redis broker task",
        "nginx proxy timeout 504 gateway load_balancer",
        "logging structured json elasticsearch kibana observability",
        "security xss csrf sql_injection sanitization owasp",
        "performance optimization profiling cprofile memory leak",
        "ci cd github_actions workflow pipeline deployment",
        "configuration environment variable dotenv secrets",
    ]
    pl_topics = [
        "baza danych postgres połączenie timeout",
        "logowanie autoryzacja jwt token formularz",
        "pamięć podręczna redis cache klucz ttl",
        "walidacja błąd error backend frontend",
        "kolejka worker zadanie proces asynchroniczny",
    ]
    all_topics = topics + pl_topics
    candidates = []
    for i in range(n):
        topic = all_topics[i % len(all_topics)]
        words = topic.split()
        # Add some noise
        noise_len = rng.randint(5, 20)
        noise_words = [rng.choice(["system", "module", "handler", "service", "config",
                                    "model", "view", "controller", "util", "helper"])
                       for _ in range(noise_len)]
        body = topic + " " + " ".join(noise_words)
        mem_id = f"mem-synth-{i:05d}"
        mtype = rng.choice(["decision", "knowledge", "gotcha", "failure", "hypothesis"])
        status = "active" if rng.random() > 0.15 else "tentative"
        created = f"2024-{rng.randint(1, 8):02d}-{rng.randint(1, 28):02d}"
        text = _make_fm(mem_id, mtype, status, created) + body + "\n"
        fm = irag.parse_fm(text)
        p = HERE / f"synth_{i:05d}.md"
        candidates.append((p, text, fm))
    return candidates


# Ground-truth queries: (query, expected_topic_keyword that must be in top results)
GROUND_TRUTH = [
    ("asyncpg pool timeout", "asyncpg"),
    ("jwt token refresh", "jwt"),
    ("redis cache ttl", "redis"),
    ("docker kubernetes", "docker"),
    ("graphql rate_limit", "graphql"),
    ("webpack eslint", "webpack"),
    ("pytest fixture", "pytest"),
    ("alembic rollback", "alembic"),
    ("celery rabbitmq", "celery"),
    ("nginx 504", "nginx"),
    ("baza danych postgres", "postgres"),
    ("logowanie formularz", "logowanie"),
    ("pamięć podręczna redis", "redis"),
    ("walidacja błąd", "walidacja"),
]


def evaluate(candidates: List[Tuple[Path, str, Dict[str, Any]]],
             limit: int = 10) -> Dict[str, Any]:
    """Run ground-truth queries and compute Recall@K, MRR."""
    cfg = {"retrieval": {"limit": limit, "mmr_lambda": 1.0, "min_score": 0.0,
                          "bm25_k1": 1.5, "bm25_b": 0.75}}
    recalls = {1: 0, 3: 0, 5: 0}
    mrr_sum = 0.0
    n_queries = 0
    latencies: List[float] = []
    for query, expected_keyword in GROUND_TRUTH:
        t0 = time.perf_counter()
        results = irag.bm25_search(query, candidates, limit, cfg)
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000)
        n_queries += 1
        # Check if expected keyword appears in any result's text
        found_at = None
        for rank, (score, p, fm, snip, matched) in enumerate(results, 1):
            if expected_keyword in snip.lower() or expected_keyword in str(fm.get("id", "")).lower():
                found_at = rank
                break
        if found_at is not None:
            mrr_sum += 1.0 / found_at
            for k in recalls:
                if found_at <= k:
                    recalls[k] += 1
    n = n_queries or 1
    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95_idx = int(len(latencies) * 0.95)
    p95 = latencies[min(p95_idx, len(latencies) - 1)] if latencies else 0
    return {
        "corpus_size": len(candidates),
        "n_queries": n_queries,
        "recall@1": round(recalls[1] / n, 4),
        "recall@3": round(recalls[3] / n, 4),
        "recall@5": round(recalls[5] / n, 4),
        "mrr": round(mrr_sum / n, 4),
        "latency_p50_ms": round(p50, 3),
        "latency_p95_ms": round(p95, 3),
    }


def main() -> int:
    print("INTERNAL_RAG Retrieval Benchmark")
    print("=" * 60)
    results = []
    for size in [100, 1000, 10000]:
        print(f"\nGenerating corpus: {size} memories...")
        corpus = generate_corpus(size)
        print(f"Running {len(GROUND_TRUTH)} ground-truth queries...")
        r = evaluate(corpus)
        results.append(r)
    # Print JSON
    print("\n" + "=" * 60)
    print("JSON results:")
    print(json.dumps(results, indent=2))
    # Print table
    print("\n" + "=" * 60)
    print(f"{'Corpus':>8}  {'Recall@1':>9}  {'Recall@3':>9}  {'Recall@5':>9}  {'MRR':>6}  {'p50(ms)':>8}  {'p95(ms)':>8}")
    print("-" * 72)
    for r in results:
        print(f"{r['corpus_size']:>8}  {r['recall@1']:>9.2%}  {r['recall@3']:>9.2%}  "
              f"{r['recall@5']:>9.2%}  {r['mrr']:>6.3f}  {r['latency_p50_ms']:>8.1f}  {r['latency_p95_ms']:>8.1f}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())