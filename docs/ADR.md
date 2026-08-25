# Architecture Decision Records (v1.6.0)

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
(`2026-07-28` and `2024-11-05`…`2025-11-25`; the full set is the canonical
`SUPPORTED_VERSIONS` constant in `irag_mcp_protocol.py`) and keeps stdout
pure. Verified against the official `mcp>=2,<3` client in
`tests/test_mcp_sdk_compat.py`.

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

## ADR-010 — Dual-era MCP: legacy + 2026-07-28, no mandatory SDK

**Decision.** The stdio MCP server supports both legacy protocol versions
(`2024-11-05`…`2025-11-25`) and the modern `2026-07-28` era
(`server/discover` without `initialize`, per-request `_meta`, `resultType`,
`structuredContent`, `outputSchema`, `ttlMs`/`cacheScope`). The full supported
version set is `2026-07-28`, `2025-11-25`, `2025-06-18`, `2025-03-26`,
`2024-11-05` (canonical constant in `irag_mcp_protocol.py::SUPPORTED_VERSIONS`).

**Why.** Existing clients (Claude Code, Cursor) use the legacy lifecycle and
must not break. Modern clients can skip `initialize` and use `discover`.
Supporting both in one stdlib-only server is cheap and avoids a migration
cliff.

**Consequences.** `irag_mcp_protocol.py` centralizes version negotiation,
`discover_result`, `tools_list_result`, and `tool_call_result` envelopes so
the server and router do not duplicate logic. The canonical supported-version
constant lives in `irag_mcp_protocol.py::SUPPORTED_VERSIONS`; documentation and
tests reference it rather than duplicating the array. Legacy `initialize`
still works for modern clients (dual-era). `confidence_kind: "heuristic"`
labels `retrieval_confidence` honestly until a calibration benchmark exists.

## ADR-011 — Adaptive retrieval is opt-in, benchmark-gated

**Decision.** `retrieval.mode: adaptive` runs sparse first and only invokes
dense if sparse evidence is weak/ambiguous (explicit heuristics:
`min_top_score`, `margin`, `min_matched`). It is **not** the default.

**Why.** Dense retrieval costs latency and a model download. On the benchmark
corpus, adaptive matches sparse quality with no measurable dense invocations
(embeddings off in CI), so there is no quality regression and no latency win
to claim yet. Recommending adaptive as default would require a benchmark on
a real corpus where dense actually fires and shows a quality gain.

**Consequences.** Adaptive stays opt-in until a benchmark proves a quality
gain or a latency reduction in dense invocations. The heuristics are
documented and tested in `memory_quality_benchmark.py`.

## ADR-012 — Bounded link-aware context, no graph DB

**Decision.** `context` may expand base results by one hop over existing
frontmatter links (`links`, `supersedes`, `derived_from`, `superseded_by`)
with a hard budget (`max_hops=1`, `max_neighbors_per_memory=2`,
`max_linked_results=3`). Linked results carry provenance
(`retrieval_reason: linked_from`) and cannot resurrect archived/invalid
records.

**Why.** Coding memory is graph-shaped (decision → derived knowledge →
failure → fix), but a graph DB violates ADR-004. A bounded 1-hop expansion
over frontmatter is cheap, deterministic, and safe.

**Consequences.** `search` is unchanged by default (opt-in only). Cycle
guard prevents A→B→A. Temporal search respects validity windows on linked
results too.

## ADR-013 — `consolidate --prepare` is read-only, no LLM

**Decision.** `consolidate --prepare` emits a deterministic JSON segment
packet (objective, completed, decisions, failures/gotchas, changed files,
checkpoint metadata) for an already-running agent to decide whether to call
`remember`. It never writes memories, calls an LLM, or deletes history.

**Why.** Segment-level memory candidates are useful for session handoff, but
auto-writing memories from a heuristic packet is a data-quality risk and an
LLM dependency the project will not take.

**Consequences.** The packet is a suggestion, not a memory. The agent is the
authority on what is durable.

## ADR-014 — Router keeps fresh-subprocess-per-call (no pool yet)

**Decision.** `irag_mcp_router.py` keeps spawning a fresh `irag.py mcp`
subprocess per `tools/call`. `tests/router_latency_benchmark.py` measures
the overhead.

**Why.** The benchmark showed ~64ms mean overhead per call (subprocess
startup + JSON forwarding), below the 100ms threshold that would warrant a
persistent child pool. A pool would complicate isolation and lifecycle for
no measured gain.

**Consequences.** If a future benchmark on a larger corpus or slower machine
shows >100ms overhead, an ADR/proposal for a pool should be written first —
not implemented inline.

## ADR-015 — Retrieved memory is untrusted evidence (trust boundary)

**Decision.** Every retrieved durable memory is wrapped in an explicit trust
boundary that marks it as `trust: untrusted` evidence, never instructions.
The context packet prints a `SECURITY NOTICE` header and delimits each memory
with `=== BEGIN INTERNAL_RAG MEMORY ===` / `=== END INTERNAL_RAG MEMORY ===`.
Structured JSON / MCP `structuredContent` carries `"trust": "untrusted"` on
the containing packet and on each result record. An optional deterministic
regex heuristic exposes `security_flags: ["instruction_like_content"]` when
the content matches high-signal instruction-like phrases (`SYSTEM:`,
`ignore previous instructions`, `you are now`, …).

**Why.** Durable memory is user-writable and persists across sessions; an
adversary (or a careless user) can store prompt-injection text in a memory.
Agents consuming retrieved memories must treat the content as data, not as
instructions that can override system/developer/user authority.

**Consequences.** The durable Markdown is NOT altered to store the field —
`trust` is derived at retrieval time. The `security_flags` heuristic is a
WARNING ONLY, not a classifier: absence of the flag MUST NOT be interpreted
as "trusted". The heuristic never blocks, rewrites, or removes the original
text. No guardrail model is introduced; no external dependency is added.
Adversarial tests in `tests/test_trust_boundary.py` verify the boundary is
present, the flag fires on poisoned text, the text remains data, and no MCP
protocol response is corrupted.

## ADR-016 — Evidence freshness is derived metadata, not persisted

**Decision.** Retrieval/context may expose `evidence_state` for each result:
`present` / `missing` / `unverifiable`. It is DERIVED at retrieval time from
the current project root + the evidence string, never persisted to Markdown
or SQLite. No schema migration is required.

**Why.** Evidence liveness is a function of the current filesystem state, not
of the memory itself. Storing it would immediately go stale and require a
sweeper. Deriving it cheaply (a single `exists()` check on a project-local
path) keeps it correct and avoids a background watcher.

**Consequences.** `evidence_state` does NOT influence ranking (by design —
provenance only, for agent reasoning). Path traversal is contained: absolute
paths and paths that escape the project root are reported as `unverifiable`,
never inspected. Symlinks are resolved and tested explicitly. No network
requests, no content hashing, no per-result Git command.
