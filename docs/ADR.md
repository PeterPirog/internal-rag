# Architecture Decision Records (v1.5.0)

This project is local, offline-first, persistent project memory for terminal
coding agents. The following decisions are deliberate. "Memory is evidence,
not authority" — and the tooling stays small enough to be audited.

Each ADR is a summary of a decision already reflected in the code; the code
and tests are the source of truth.

---

## ADR-001 — Markdown is the source of truth; SQLite is a cache

**Decision.** Durable memory lives in `INTERNAL_RAG/**/*.md` frontmatter +
body. SQLite (`.index.sqlite3`) is only a local index / embedding cache /
usage store.

**Why.** Markdown is human-readable, git-diffable, portable, and survives a
deleted database. The index is rebuilt from Markdown (`index --rebuild`).
Usage and embeddings are *derived* state and must never be the only copy of
anything.

**Consequences.** Search must work with the index absent (it does — pure
BM25). `content_hash` excludes `last_accessed`/`access_count` so usage never
invalidates embeddings.

## ADR-002 — Zero required runtime dependencies

**Decision.** The core CLI, retrieval (BM25 + MMR), and both MCP servers
(`irag.py mcp`, `irag_mcp_router.py`) use only the Python 3.8+ standard
library.

**Why.** Agents run on many machines, often air-gapped. A mandatory dependency
turns a "memory" helper into a supply-chain and install burden.

**Consequences.** The YAML config is parsed by a documented subset parser
(`parse_yaml_simple`), not PyYAML. Embeddings are strictly optional
(ADR-003). This is enforced by CI compiling and running the full suite without
any `pip install`.

## ADR-003 — Embeddings are optional, not default-on

**Decision.** Dense retrieval activates only when `sentence-transformers` is
installed **and** the mode/profile is configured to use it. Otherwise the
sparse (BM25) channel is authoritative.

**Why.** Reproducibility and determinism without a heavy model download.
Benchmarks on small corpora show dense adds little over sparse for the cost.

**Consequences.** Two retrieval profiles exist (`english-fast`,
`multilingual`); cache keys embed model identity so profiles never share
vectors.

## ADR-004 — No vector DB / graph DB / background daemon

**Decision.** INTERNAL_RAG does not use Qdrant/Chroma/Weaviate/Milvus,
Neo4j, Redis, or any long-running process.

**Why.** Those trade local simplicity and offline operation for scale that a
per-project memory store does not need. A background service is a privacy and
lifecycle liability the project explicitly avoids.

**Consequences.** Scale is bounded by the on-disk Markdown corpus and SQLite
FTS5. `sqlite-vec` was evaluated and **rejected** — benchmarks did not show
the dense scan as a bottleneck, so it would add a dependency for no measured
gain.

## ADR-005 — MCP via minimal stdio, no mandatory SDK

**Decision.** The MCP server is a hand-rolled, newline-delimited JSON-RPC 2.0
stdio server. The optional `mcp` SDK is used **only** to prove interoperability
in CI, never as a runtime dependency.

**Why.** A stdio JSON-RPC server is trivially auditable and has zero
dependencies. Requiring the SDK would break ADR-002 and the offline story.

**Consequences.** The server negotiates protocol versions
(`2025-11-25` … `2024-11-05`) and keeps stdout pure. Verified against the
official `mcp>=2,<3` client in `tests/test_mcp_sdk_compat.py`.

## ADR-006 — Multi-project via a router, not a shared store

**Decision.** Each project keeps its own `INTERNAL_RAG/`. A single MCP client
reaches several projects through `irag_mcp_router.py`, which spawns an
isolated `irag.py mcp` subprocess per call with `cwd=<project root>`.

**Why.** Cross-project isolation is a hard requirement. A shared database or a
single in-process server would leak one project's memory into another. The
subprocess boundary makes isolation structural, not conventional.

**Consequences.** A registry allowlist + `write:false` gate; a read-only
project can never be mutated via MCP. Enforced by
`tests/test_mcp_router.py::test_isolation_between_projects`.

## ADR-007 — Retrieval abstention is evidence-based, not score-based

**Decision.** The admission gate decides whether a candidate is admitted on
**raw retrieval evidence** (a sparse token actually present, or a calibrated
dense score), before any policy boost. Low absolute scores are not, by
themselves, a rejection — RRF scores are tiny and non-comparable.

**Why.** Agents must be able to tell "no usable answer" apart from a weak hit.
A global score threshold is arbitrary and breaks across profiles; evidence is
explainable and per-candidate.

**Consequences.** `search --json --meta` exposes `abstained`,
`retrieval_confidence`, and a human `reason`. `min_dense_score` stays `null`
(accept-as-is) until a per-profile calibration is benchmarked.

## ADR-008 — The FTS5 prefilter is a superset accelerator

**Decision.** The FTS5 prefilter returns FTS5 top-n **union** Python BM25
top-k. It narrows the scoring pool but must never change the final ranking or
drop a hit the full scan would return.

**Why.** A prefilter that can lose recall is a correctness bug, not an
optimization. The union guarantees monotonicity; the freshness guard
(memory newer than index) guarantees we never serve stale candidates.

**Consequences.** When in doubt (no index, stale, tiny corpus, FTS5 missing),
the system falls back to the full scan and preserves the exact prior behavior.

## ADR-009 — Consolidation and lifecycle are read-only

**Decision.** `consolidate` and the temporal lifecycle report and recommend;
they never delete or rewrite memory. Superseding links A→B and preserves A.

**Why.** History is a first-class asset. An autonomous cleanup pass is a
data-loss risk the project will not take.

**Consequences.** `consolidate --json` emits a `plan` for the agent to
evaluate; the agent decides. `forget` archives, it does not delete.
