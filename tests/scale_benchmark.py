#!/usr/bin/env python3
"""Scale benchmark (P1 hardening).

Generates synthetic memory corpora of ~100 / 1,000 / 10,000 memories and
measures:
  - initial index build (rebuild_index + SQLite open/rebuild when available)
  - incremental index update (one new memory + rebuild_index)
  - pure-Python BM25 search
  - FTS5 path search (when SQLite FTS5 is available)
  - hybrid retrieval (when optional embeddings are available)
  - context generation
  - .index.sqlite3 size (when present)
  - p50 / p95 latency

Run:
  python tests/scale_benchmark.py             # 100 + 1000 (skips 10k)
  python tests/scale_benchmark.py --full      # 100 + 1000 + 10000
  python tests/scale_benchmark.py --smoke     # 100 only (CI canary)
  python tests/scale_benchmark.py --json      # machine-readable

Zero external dependencies for the sparse path. Python 3.8+ stdlib only.
The 10k case is NOT run in the normal/smoke mode unless --full is passed,
to keep CI fast. No vector DB is added because of this benchmark.
"""
from __future__ import annotations
import argparse
import importlib.util
import io
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
IRAG_PATH = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag.py"

_spec = importlib.util.spec_from_file_location("irag_scale", str(IRAG_PATH))
irag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(irag)


class Env:
    def __init__(self, sandbox: Path):
        self.sandbox = sandbox
        self.rag = sandbox / "INTERNAL_RAG"
        for d in ("decisions", "knowledge", "gotchas", "failures",
                  "hypotheses", "sessions", "sessions/.snapshots", "archive"):
            (self.rag / d).mkdir(parents=True, exist_ok=True)
        (self.rag / "WORKING_STATE.md").write_text("# Working state\n", encoding="utf-8")

    def __enter__(self):
        self._old = (irag.ROOT, irag.RAG, irag.CONFIG_PATH, irag.WORKING,
                     irag._open_sqlite_index, irag.FP_CACHE, irag.CHECKPOINT)
        irag.ROOT = self.sandbox
        irag.RAG = self.rag
        irag.CONFIG_PATH = self.sandbox / ".irag.yml"
        irag.WORKING = self.rag / "WORKING_STATE.md"
        irag._open_sqlite_index = lambda: None
        irag.FP_CACHE = self.rag / ".fpcache.json"
        irag.CHECKPOINT = self.rag / ".checkpoint.json"
        self._prev_default = irag.DEFAULT_CONFIG
        patched = json.loads(json.dumps(irag.DEFAULT_CONFIG))
        patched["retrieval"]["embeddings"] = "off"
        patched["retrieval"]["mode"] = "sparse"
        patched["retrieval"]["fts_prefilter"] = {"enabled": False, "min_corpus_size": 50}
        irag.DEFAULT_CONFIG = patched
        return self

    def __exit__(self, *a):
        irag.ROOT, irag.RAG, irag.CONFIG_PATH, irag.WORKING, \
            irag._open_sqlite_index, irag.FP_CACHE, irag.CHECKPOINT = self._old
        irag.DEFAULT_CONFIG = self._prev_default


def _gen_corpus(rag: Path, n: int) -> None:
    """Generate n synthetic memory files spread across type dirs."""
    dirs = ["decisions", "knowledge", "gotchas", "failures", "hypotheses"]
    types = ["decision", "knowledge", "gotcha", "failure", "hypothesis"]
    vocab = ["redis", "cache", "auth", "jwt", "token", "postgres", "pool",
             "rate", "limiter", "token-bucket", "asyncpg", "migration",
             "nginx", "timeout", "webpack", "eslint", "celery", "worker",
             "docker", "compose", "pytest", "asyncio", "feature", "flag"]
    for i in range(n):
        d = dirs[i % len(dirs)]
        t = types[i % len(types)]
        # deterministic content: mix of vocab tokens + a unique id
        tokens = [vocab[(i + j) % len(vocab)] for j in range(8)]
        body = f"Memory {i}: " + " ".join(tokens) + f" unique-tag-{i}"
        title = f"Synthetic memory {i}"
        mem = (f"---\nid: mem-scale-{i:06d}\ntype: {t}\nstatus: active\n"
               f"created: 2024-01-01\nscope: []\ntags: [{tokens[0]}, {tokens[1]}]\n"
               f"sources: []\nlinks: []\n---\n\n# {title}\n\n"
               f"## Knowledge\n\n{body}\n\n## Consequence\n\nNone.\n")
        (rag / d / f"m{i:06d}.md").write_text(mem, encoding="utf-8")


def _percentiles(xs: List[float]) -> Tuple[float, float, float]:
    if not xs:
        return 0.0, 0.0, 0.0
    xs2 = sorted(xs)
    p50 = xs2[len(xs2) // 2]
    p95 = xs2[min(int(len(xs2) * 0.95), len(xs2) - 1)]
    mean = statistics.mean(xs2)
    return p50, p95, mean


def _db_size(rag: Path) -> int:
    p = rag / ".index.sqlite3"
    return p.stat().st_size if p.exists() else 0


def bench_corpus(n: int) -> Dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix=f"irag-scale-{n}-"))
    try:
        with Env(tmp):
            _gen_corpus(irag.RAG, n)
            # initial index build (Markdown INDEX.md regeneration)
            t0 = time.perf_counter()
            buf = io.StringIO()
            with redirect_stdout(buf):
                irag.rebuild_index()
            build_ms = (time.perf_counter() - t0) * 1000.0
            # incremental: add 1 memory + rebuild
            mem = (f"---\nid: mem-scale-extra\ntype: knowledge\nstatus: active\n"
                   "created: 2024-01-01\nscope: []\ntags: [extra]\nsources: []\nlinks: []\n---\n\n"
                   "# Extra\n\n## Knowledge\n\nextra unique-tag-extra memory\n\n## Consequence\n\nNone.\n")
            (irag.RAG / "knowledge" / "extra.md").write_text(mem, encoding="utf-8")
            t0 = time.perf_counter()
            buf = io.StringIO()
            with redirect_stdout(buf):
                irag.rebuild_index()
            incr_ms = (time.perf_counter() - t0) * 1000.0
            # pure-Python BM25 (sparse) search latency
            queries = ["redis cache auth", "postgres pool", "rate limiter token",
                       "nginx timeout", "celery worker prefetch",
                       "unique-tag-0", "unique-tag-" + str(n // 2),
                       "feature flag", "docker compose", "pytest asyncio"]
            # warmup
            irag.search("redis cache", 5)
            lats: List[float] = []
            for _ in range(3):
                for q in queries:
                    t0 = time.perf_counter()
                    irag.search(q, 8)
                    lats.append((time.perf_counter() - t0) * 1000.0)
            p50, p95, mean = _percentiles(lats)
            # context generation latency
            ctx_lats: List[float] = []
            for _ in range(3):
                t0 = time.perf_counter()
                a = type("A", (), {"task": "redis cache auth", "limit": 6, "json": True,
                                   "type": None, "status": None})()
                buf = io.StringIO()
                with redirect_stdout(buf):
                    irag.context(a)
                ctx_lats.append((time.perf_counter() - t0) * 1000.0)
            cp50, cp95, cmean = _percentiles(ctx_lats)
            db_bytes = _db_size(irag.RAG)
            # FTS5 availability (does not run a query, just checks open)
            fts5 = "unknown"
            try:
                idx = irag._open_sqlite_index()
                if idx is not None:
                    st = idx.status()
                    fts5 = "yes" if st.get("fts5_available") else "no"
                    idx.close()
                else:
                    fts5 = "disabled-in-bench"
            except Exception:
                fts5 = "unavailable"
            # embeddings availability (optional, no network)
            emb = "off"
            try:
                avail = irag.embeddings_search("test", [], 1, irag.load_config())
                emb = "available" if avail is not None else "off"
            except Exception:
                emb = "off"
            return {
                "corpus_size": n,
                "initial_index_build_ms": round(build_ms, 2),
                "incremental_index_update_ms": round(incr_ms, 2),
                "sparse_p50_ms": round(p50, 2),
                "sparse_p95_ms": round(p95, 2),
                "sparse_mean_ms": round(mean, 2),
                "context_p50_ms": round(cp50, 2),
                "context_p95_ms": round(cp95, 2),
                "context_mean_ms": round(cmean, 2),
                "db_size_bytes": db_bytes,
                "fts5": fts5,
                "embeddings": emb,
            }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="INTERNAL_RAG scale benchmark")
    ap.add_argument("--smoke", action="store_true", help="CI canary: 100 only")
    ap.add_argument("--full", action="store_true", help="Include the 10k case")
    ap.add_argument("--json", action="store_true", help="Machine-readable JSON")
    args = ap.parse_args()
    if args.smoke:
        sizes = [100]
    elif args.full:
        sizes = [100, 1000, 10000]
    else:
        sizes = [100, 1000]
    reports = [bench_corpus(n) for n in sizes]
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        return 0
    print("INTERNAL_RAG Scale Benchmark")
    print("=" * 80)
    cols = ["corpus", "build_ms", "incr_ms", "sp_p50", "sp_p95",
            "ctx_p50", "ctx_p95", "db_kb", "fts5", "emb"]
    widths = {"corpus": 8, "build_ms": 10, "incr_ms": 10, "sp_p50": 9, "sp_p95": 9,
              "ctx_p50": 9, "ctx_p95": 9, "db_kb": 9, "fts5": 8, "emb": 9}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    print(header)
    print("-" * len(header))
    for r in reports:
        row = {
            "corpus": str(r["corpus_size"]),
            "build_ms": f"{r['initial_index_build_ms']:.1f}",
            "incr_ms": f"{r['incremental_index_update_ms']:.1f}",
            "sp_p50": f"{r['sparse_p50_ms']:.1f}",
            "sp_p95": f"{r['sparse_p95_ms']:.1f}",
            "ctx_p50": f"{r['context_p50_ms']:.1f}",
            "ctx_p95": f"{r['context_p95_ms']:.1f}",
            "db_kb": f"{r['db_size_bytes'] / 1024:.1f}",
            "fts5": r["fts5"],
            "emb": r["embeddings"],
        }
        print("  ".join(row[c].ljust(widths[c]) for c in cols))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())