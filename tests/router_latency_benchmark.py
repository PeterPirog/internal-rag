#!/usr/bin/env python3
"""Router latency benchmark (CEL J).

Compares direct `irag.py mcp` vs `irag_mcp_router.py` (fresh subprocess per
call) for sparse retrieval. Reports p50/p95 latency so we can decide whether
a persistent child pool is warranted (per CEL J: do NOT implement a pool
unless the benchmark shows startup is a real problem).

Zero dependencies. Stdlib only.
"""
from __future__ import annotations
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
IRAG = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag.py"
ROUTER = PROJECT_ROOT / ".agents" / "skills" / "internal-rag" / "irag_mcp_router.py"


def _make_proj(tmp: Path) -> Path:
    rag = tmp / "INTERNAL_RAG"
    for d in ("decisions", "knowledge", "gotchas", "failures", "hypotheses",
              "sessions/.snapshots", "archive"):
        (rag / d).mkdir(parents=True, exist_ok=True)
    (rag / "WORKING_STATE.md").write_text("# Working state\n", encoding="utf-8")
    for i in range(10):
        (rag / "knowledge" / f"m{i}.md").write_text(
            f"---\nid: m{i}\ntype: knowledge\nstatus: active\ncreated: 2024-01-01\n"
            f"scope: []\ntags: [topic{i}]\nsources: []\nlinks: []\n---\n\n"
            f"# Memory {i}\n\n## Knowledge\n\nTopic {i} content about redis cache pool auth.\n",
            encoding="utf-8")
    return tmp


def _stdio_call(args: list, lines: list, cwd: Path) -> float:
    stdin = "\n".join(json.dumps(l) for l in lines) + "\n"
    t0 = time.perf_counter()
    subprocess.run(args, input=stdin, cwd=str(cwd),
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                   text=True, encoding="utf-8", timeout=60)
    return (time.perf_counter() - t0) * 1000.0


def bench_direct(tmp: Path, n: int = 20) -> list:
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "search", "arguments": {"query": "redis cache"}}},
        {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
    ]
    return [_stdio_call([sys.executable, str(IRAG), "mcp"], lines, tmp) for _ in range(n)]


def bench_router(tmp: Path, reg: Path, n: int = 20) -> list:
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "search", "arguments": {"project": "demo", "query": "redis cache"}}},
        {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
    ]
    return [_stdio_call([sys.executable, str(ROUTER), "--registry", str(reg)], lines, tmp)
            for _ in range(n)]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="irag-router-bench-"))
    try:
        _make_proj(tmp)
        reg = tmp / "reg.json"
        reg.write_text(json.dumps({"projects": {"demo": {"root": str(tmp), "write": False}}}),
                       encoding="utf-8")
        print("Router latency benchmark (CEL J): direct vs router, sparse")
        print("=" * 64)
        n = 15
        d = sorted(bench_direct(tmp, n))
        r = sorted(bench_router(tmp, reg, n))
        print(f"{'':16} {'p50(ms)':>10} {'p95(ms)':>10} {'mean(ms)':>10} {'min':>8} {'max':>8}")
        print("-" * 64)
        for label, xs in [("direct server", d), ("router (subprocess)", r)]:
            p50 = xs[len(xs) // 2]
            p95 = xs[min(int(len(xs) * 0.95), len(xs) - 1)]
            mean = statistics.mean(xs)
            print(f"{label:16} {p50:>10.1f} {p95:>10.1f} {mean:>10.1f} {min(xs):>8.1f} {max(xs):>8.1f}")
        overhead = statistics.mean(r) - statistics.mean(d)
        print(f"\nrouter overhead (mean): {overhead:.1f} ms/call")
        print(f"overhead is subprocess startup + JSON forwarding (expected for the isolation model)")
        print(f"\nDecision: a persistent child pool is {'WARRANTED' if overhead > 100 else 'NOT warranted'} "
              f"by this benchmark (threshold: 100ms).")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())