# Changelog

## 1.8.1 — 2026-08-26

Hardening release: MCP protocol-era separation, per-request client-capabilities validation, OpenCode 2 runtime plugin API, ProjectWriteLock ownership + stale-lock theft prevention, GC/retention fixes, ephemeral lifecycle e2e, config validation. 401 tests green (0 fail, 5 skipped). No new runtime dependencies (stdlib only, Python 3.8+).

### P1/P21 — OpenCode V1/V2 config split + CI
- Installer `register_client()`/`unregister_client()`/`_verify_registered_server()` per-client (V1 `enabled: true`, V2 `disabled` absent = enabled).
- 8 V1/V2 golden tests (`tests/test_install_cli.py`).
- CI red fix: router name `mcp-light-memory-router`.

### P2/P3 — OpenCode 2 plugin runtime API
- V2 plugin (`internal-rag-resilience-v2.ts`) rewritten to `Plugin.define({ id, setup(ctx) })` + `ctx.tool.hook("execute.after")` + `ctx.session.hook(...)` (documented V2 event names only).
- V1 plugin unchanged (hooks-object API).
- Installer selects exactly one plugin per client.
- Issue #44788 documented as known V2 event-delivery limitation; MCP pull-based workflow is the primary resilience path.

### P4/P5/P6 — MCP protocol era separation + validation
- `SUPPORTED_MODERN_VERSIONS = ["2026-07-28"]` and `SUPPORTED_LEGACY_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]` as explicit lists.
- `server/discover` advertises ONLY modern revisions (legacy not advertised).
- `initialize` negotiates ONLY legacy revisions (2026-07-28 counter-offers to 2025-11-25).
- Modern per-request `_meta` validated by a single shared validator (`irag_mcp_protocol.validate_modern_request`):
  - unsupported modern version → `-32022` with `supported`/`requested` data.
  - missing/wrong-type `clientCapabilities` → JSON-RPC `-32602` (invalid params). Empty `{}` accepted.
  - legacy requests (no `_meta`) pass through untouched.
- Router enforces identical rules.
- 46 conformance tests (`TestEraSeparation`, `TestRouterEraSeparation`, `TestClientCapabilitiesValidation`, `TestRouterClientCapabilitiesValidation`).

### P7/P8/P20 — Ephemeral lifecycle CLI + e2e
- CLI commands `observe` (ephemeral store), `promote` (distill → admission → durable → raw deletion), `gc` (plan/dry-run/apply with ephemeral + snapshot GC).
- Provenance frontmatter: `source_observation`, `obs_content_hash` on durable memories.
- End-to-end lifecycle test (`tests/test_e2e_lifecycle.py`): observe → promote → durable memory → raw deletion → searchable; benign output not promoted; expired observations rejected; `gc --apply` archives stale low-value memory with `archived_at` + `status: archived`; dry-run does not move.
- `_last_json` parser handles JSON arrays (search) and objects.

### P10–P15 — GC/retention hardening
- `last_accessed` normalized by `_parse_ts` (ISO date string or epoch).
- Archive metadata stamped BEFORE move (`archived_at` + `status: archived`) — crash-safe.
- `deprioritize` writes `priority: low` frontmatter; retrieval `_policy_boost` applies `-2.0` penalty.
- `gc --apply` runs under `ProjectWriteLock` (atomic, serialized).
- Snapshot GC (byte-level enforcement).
- `DEFAULT_CONFIG` includes `ephemeral` + `gc` sections; `_validate_config` accepts them as known sections.

### P-Lock — ProjectWriteLock ownership + stale-lock theft prevention
- Lock file now contains PID + timestamp + random ownership token (`secrets.token_hex`) + process creation epoch.
- `release()` unlinks ONLY if the token in the file still matches this object's token (prevents foreign unlock: a stale owner cannot delete a new owner's lock).
- A dead PID is always reclaimable (regardless of age); a live PID is NEVER stolen on age alone (any platform).
- Windows liveness via `OpenProcess` + `GetExitCodeProcess` (ctypes over kernel32, stdlib only); `STILL_ACTIVE` (259) vs real exit code; PID reuse guarded by creation-epoch comparison.
- POSIX: `os.kill(pid, 0)`; `flock` advisory lock as belt-and-braces.
- Multiprocess tests: live holder not stolen on age; dead holder reclaimable; stale owner release does not stomp new owner; dead stale PID reclaimed; fresh-timestamp dead PID reclaimed.

## 1.8.0 — 2026-08-26

Major modernization: MCP 2026-07-28 final spec compliance, OpenCode 1/2 split, ephemeral memory lifecycle, diagnostic distillation, GC/retention, atomic writes.

### P0 — MCP 2026-07-28 final wire format compliance
- **Per-request protocol version** read from `_meta["io.modelcontextprotocol/protocolVersion"]` (NOT `params.protocolVersion` as in the draft).
- **`server/discover`** reads version from `_meta`, returns `serverInfo` in `_meta["io.modelcontextprotocol/serverInfo"]` (NOT top-level).
- **`ttlMs`/`cacheScope`** are top-level result fields (NOT in `_meta`). Values: `"public"` | `"private"`.
- **`resultType`** required on every result.
- **`outputSchema`** declared in tool definitions (NOT in `tools/call` results).
- **Stateless dispatch**: modern requests are self-describing per-request; no `conn_version` needed.
- **`UnsupportedProtocolVersionError`** uses code `-32022` with `supported`/`requested` data.
- Legacy `initialize` still works (dual-era). Legacy `initialize` returns `serverInfo` top-level (backward compat).
- Router updated to the same wire format.
- **21 conformance/golden tests** (`tests/test_mcp_conformance.py`) based on the official spec.

### P0 — OpenCode 1 vs OpenCode 2 split
- `--client opencode` = stable OpenCode 1 (uses `enabled: true` on server entry).
- `--client opencode2` = OpenCode 2 beta (no `enabled` field; V2 uses `disabled` with absent = enabled).
- Both write `opencode.json` with `mcp.servers.<name>` shape, `type: "local"`, `command` as array, `cwd`.
- Merge preserves existing MCP servers and other config keys.
- OpenCode plugin V1 (`internal-rag-resilience.ts`) and V2 (`internal-rag-resilience-v2.ts`) split.
- V2 plugin uses best-effort `ctx.tool.hook` / `ctx.event` patterns (beta API, may change).

### P1 — Ephemeral observations layer (`irag_ephemeral.py`)
- SQLite-based bounded storage for raw tool outputs (console, terminal, builds, lints, tests).
- NOT durable Markdown memory; NOT indexed for retrieval.
- TTL-based expiry (default 30 min, configurable via `ephemeral.*`).
- `max_records` (200) and `max_bytes` (2MB) limits. `max_record_bytes` (64KB) per observation.
- Secret redaction (password=, api_key=, token=, etc.).
- Lifecycle: raw → ephemeral → distillation → admission → durable → deletion.
- Promotion marks observation + deletes after durable memory created.

### P1 — Diagnostic distillation (`irag_distill.py`)
- Stdlib-first extraction from large tool outputs (no LLM dependency).
- Extracts: command name, exit code, ERROR/WARNING/FAILED, exception type+message, stack frames, root cause, remediation, evidence excerpt, content hash.
- `should_promote` only if confidence ≥ MEDIUM and root_cause/errors present.
- Successful output / warnings without value → `should_promote=False`.
- 5000-line output → short conclusion like "Test X fails because Y. Root cause in Z."

### P1 — OpenCode compaction integration
- `--compaction` flag: merges compaction settings into OpenCode config (does NOT overwrite existing values).
- V1: `compaction.auto=true`, `compaction.prune=true`, `compaction.reserved=10000`.
- V2: `tool_output.max_lines=500`, `tool_output.max_bytes=65536`.
- MCP Light Memory manages its own persistent/ephemeral memory; does NOT pretend to control host conversation history.

### P1 — Retention + GC (`irag_gc.py`)
- Retention classes: `protected` (decisions/constraints — never GC'd), `tentative_hypotheses`, `normal_durable`, `archived`.
- 4-stage decay: deprioritize → archive candidate → archive → delete (after grace period).
- Factors: created, last_accessed, access_count, confidence, status, type, evidence freshness, link count, reinforcement.
- `gc --dry-run` is the safe default. `gc --apply` executes.
- Protected decisions/constraints NEVER appear in GC candidates.

### P1 — Session snapshot GC
- `snapshot_gc_plan()`: `max_age_days`, `max_count`, `max_bytes`.
- Active recovery point (most recent snapshot) is NEVER deleted.
- Dry-run report before destructive cleanup.

### P1 — Concurrency + atomic writes (`irag_atomic.py`)
- `atomic_write_text()`: temp file → fsync → `os.replace`.
- `ProjectWriteLock`: cross-platform file lock (O_EXCL + fcntl on POSIX) with stale-lock detection.
- Applied to: `save_working`, `save_checkpoint`, `_append_history`, tasks, fpcache.

### P2 — Value-aware forgetting
- `_compute_memory_value()`: recency × reuse × confidence × evidence × type × reinforcement.
- Decisions/constraints are protected; never deleted by decay alone.
- "Not accessed in 30 days" is NEVER sufficient alone for deletion.
- Value score is separate from relevance score (no benchmark mixing).

### Tests
- **340 tests pass** (was 279), 5 skipped, 0 required dependencies.
- New: `test_mcp_conformance.py` (21), `test_ephemeral_distill_atomic.py` (23), `test_gc.py` (14), `test_install_cli.py` (+3 OpenCode V1/V2 split).
- No retrieval-quality regression.

## 1.7.3 — 2026-08-26

Critical fix for JetBrains/PyCharm: `--client jetbrains` no longer claims to "register" a server, because PyCharm does NOT auto-read any MCP config file.

### Fixes
- **`--client jetbrains` no longer writes a fake config file**: PyCharm manages MCP servers exclusively through `Settings → Tools → AI Assistant → MCP` in the IDE UI. The installer now:
  - does NOT write `~/.jetbrains/mcp.json` (which the IDE ignores),
  - prints a prominent `MANUAL MCP SETUP REQUIRED` block with the ready-to-paste JSON (`command` + `args`), the exact Working Directory path, and step-by-step IDE menu instructions,
  - runs `--version` verification on the Python interpreter (so the user knows the path works before pasting it).
- **`--unregister --client jetbrains`**: now prints a reminder to remove the server manually in the IDE UI (instead of trying to delete a non-existent config file).
- **Final install message**: for jetbrains, prints `MCP setup instructions printed above (manual IDE step required)` instead of the misleading `MCP server registered`.
- **`--client` argparse help**: clarifies that jetbrains prints manual instructions, not a config file.
- Version bumped to **1.7.3**.

## 1.7.2 — 2026-08-25

Hotfix for JetBrains/PyCharm installation (feedback from real deployment).

### Fixes
- **JetBrains cwd warning**: the JetBrains MCP config file does not reliably support a `working_directory`/`cwd` field in the JSON — the IDE reads it from `Settings → Tools → AI Assistant → MCP` in the UI. `install.py --client jetbrains` now:
  - writes `working_directory` into the config as a hint (some IDE versions may read it),
  - prints a prominent `WARNING` with the exact path to set in the IDE UI,
  - so the memory store does not land in the IDE's default cwd.
- **Client-specific restart messages**: the final "Restart Warp/OpenCode..." line is now per-client (`Restart PyCharm/JetBrains IDE` for jetbrains, `Restart Warp` for warp, `Restart OpenCode` for opencode). No more confusion when reading the install log.
- **Memory store path in install output**: the install log now prints `Memory store: <abs_path>/INTERNAL_RAG` so the user can immediately verify the memory landed in the right project root.

## 1.7.1 — 2026-08-25

Hotfix for Windows installation issues found in real Warp deployment.

### Fixes
- **detect_python() — reject WindowsApps stub**: `shutil.which("python")` on Windows can return the Microsoft Store 0-byte stub in `WindowsApps\python*.exe`, which crashes with `ResourceUnavailable` when Warp tries to start the MCP server. The detector now:
  1. Prefers `py -0p` (Windows py launcher) which lists all installed Pythons with real paths, bypassing PATH entirely.
  2. Verifies each `shutil.which()` candidate by running `--version` and rejecting the WindowsApps stub via realpath check.
  3. Falls back to `sys.executable` (the running interpreter, always real).
- **Post-register verification**: after writing the client config, `install.py` immediately runs the registered interpreter with `--version` and reports `PASS` / `FAIL`. Catches a broken Python path in 1 second instead of a silent MCP failure in Warp.
- **unregister cleanup**: `--unregister` now deletes the config file if it becomes empty after removing the server (and removes the empty parent dir, e.g. `.warp/`). Fixes the dead `.warp/.mcp.json` skeleton that triggered `GUARD STALE`.
- Version bumped to **1.7.1** across `VERSION`, `irag.py`, `irag_mcp_router.py`, `install.py`, `README.md`.

## 1.7.0 — 2026-08-25

Total rebrand from `internal-rag` to **MCP Light Memory** (`mcp-light-memory`). Backward-compatible; no data migration required.

### Rebrand
- **New product name:** MCP Light Memory. New repo/product slug: `mcp-light-memory`.
- **New CLI alias:** `mlm` (`mlm.py` shim) — primary entrypoint that forwards to the canonical `irag.py` core. `irag.py` remains a supported legacy alias.
- **New MCP server display name:** `mcp-light-memory` (was `internal-rag`). Router: `mcp-light-memory-router` (was `internal-rag-router`).
- **New branding assets:** `docs/assets/logo.svg`, `docs/assets/icon.svg` (hand-written SVG, no binary blobs). Branding note: `docs/BRANDING.md`.
- **New docs:** `docs/MIGRATION-TO-MCP-LIGHT-MEMORY.md` (migration guide), `docs/GITHUB-REBRAND-CHECKLIST.md` (manual rename prep).
- **README rewritten** with centered logo, new pitch, "formerly internal-rag" note, updated badges (incl. `dependencies-0` and `MCP 2026-07-28 dual-era`).
- **Examples updated** to use `mcp-light-memory` / `mcp-light-memory-router` server keys. New router examples: `warp-router.example.json`, `opencode-v2-router.example.jsonc`, `jetbrains-router.example.json`.
- **Docs titles** bumped to v1.7.0; product-name references updated throughout.
- **AGENTS.md markers** updated to `MCP_LIGHT_MEMORY_START`/`END`; `install.py` writes the new markers and migrates old ones.
- **`.opencode/` tools + plugin + command** updated to call `mlm.py`.
- **`irag_hooks.py`** shell shims updated to call `mlm.py`.
- **CI workflow** compiles `mlm.py` and runs the mutation/scale smoke benchmarks.

### Backward compatibility (preserved)
- `irag.py` module filename kept — same canonical core, same imports.
- `INTERNAL_RAG/` storage folder kept — no data migration.
- `.irag.yml` config unchanged. `.index.sqlite3` unchanged. Stored memories unchanged.
- Old MCP server names in client configs keep working (the client-side key is user-chosen; the server's `serverInfo.name` is now `mcp-light-memory`).
- Legacy `irag` CLI command still works (same core, same exit codes, same stdout/stderr).

### Tests
- New `tests/test_rebrand.py` (rebrand consistency): version/PRODUCT_NAME constants, `mlm.py` shim forwards + help shows new brand, MCP `serverInfo.name` is `mcp-light-memory` / `mcp-light-memory-router`, examples use new server keys, router examples exist, README/docs reference new brand, logo assets exist, legacy `irag.py` alias still works.

### Acceptance
- 0 required runtime dependencies (unchanged).
- Markdown remains source of truth; SQLite remains disposable (unchanged).
- No retrieval-quality regression (unchanged).
- MCP dual-era compatibility preserved (unchanged).

## 1.6.1 — 2026-08-25

Post-v1.6 hardening: trust boundary, mutation benchmark, evidence freshness, scale benchmark, router security regressions, docs consistency.

### Trust boundary for retrieved memory (ADR-015)
- Every retrieved durable memory is now explicitly marked `trust: "untrusted"` evidence, never instructions.
- `context` text packet prints a `SECURITY NOTICE` header and delimits each memory with `=== BEGIN/END INTERNAL_RAG MEMORY ===`.
- Structured JSON / MCP `structuredContent` carries `"trust": "untrusted"` on the containing packet and on each result record.
- Optional deterministic regex heuristic exposes `security_flags: ["instruction_like_content"]` for high-signal injection-like phrases (`SYSTEM:`, `ignore previous instructions`, `you are now`, `ADMIN OVERRIDE`, …). WARNING ONLY — never blocks, rewrites, or removes the original text; absence of the flag does NOT mean trusted.
- Adversarial tests: `tests/test_trust_boundary.py` (15 tests) — poisoned text remains data, trust boundary present, flag fires, no MCP protocol response corrupted, stdout purity preserved.

### Memory mutation/lifecycle benchmark (P0)
- `tests/memory_mutation_benchmark.py` — deterministic, zero-dependency, 11 scenarios: decision replacement, failure→fix, conflicting active, archived memory, duplicate writes (exact + near), links/backlinks, invalid evidence, PL/EN mixed, export/import, index delete + rebuild, update preserves history.
- Invariants asserted: superseded memory not returned as current truth; historical retrieval still finds the old memory for a valid historical date; archived/invalid do not leak into normal active retrieval; history never silently deleted; backlinks coherent; export/import preserves lifecycle metadata; deleting `.index.sqlite3` does not change durable semantics; rebuilding the index produces equivalent retrieval results; duplicate protection deterministic.
- `--smoke` canary for CI.

### Evidence freshness (ADR-016)
- Retrieval/context exposes `evidence_state` (`present`/`missing`/`unverifiable`) for local path-like evidence.
- Derived at retrieval time from the project root + the evidence string; never persisted; no schema migration; no ranking change.
- Path-traversal-safe (absolute paths and `../../` outside root → `unverifiable`, never inspected); Windows drive-letter paths handled; symlinks resolved and tested explicitly.
- Tests: `tests/test_evidence_freshness.py` (20 tests).

### Scale benchmark (P1)
- `tests/scale_benchmark.py` — synthetic corpora of 100 / 1,000 / 10,000 memories.
- Measures: initial index build, incremental update, pure-Python BM25, FTS5 path, hybrid (when optional embeddings available), context generation, `.index.sqlite3` size, p50/p95.
- `--smoke` (100 only, CI canary), normal (100+1000), `--full` (100+1000+10000). The 10k case is NOT run in normal/smoke mode.
- No vector DB added because of this benchmark (per ADR-004).

### MCP/router security regression suite (P1)
- Extended `tests/test_mcp_router.py` (+12 tests): unknown/malformed project ids, missing root, root without INTERNAL_RAG, `write: "false"`/`0`/`1` rejected at load, cross-project search/write isolation, path traversal in project id, symlinked roots, malformed MCP arguments (non-dict), modern + legacy protocol behavior after errors, stdout purity after errors.

### Docs consistency test + drift fix (P0)
- `tests/test_docs_consistency.py` (11 tests) — validates documented project version matches canonical, MCP protocol version sets in docs do not omit supported versions, all JSON examples parse, JSONC examples validate, example filenames referenced by docs exist, router `SUPPORTED_VERSIONS` matches the canonical constant in `irag_mcp_protocol.py`.
- Canonical `SUPPORTED_VERSIONS` constant in `irag_mcp_protocol.py` is now the single source of truth referenced by ADR-005/010 and docs.
- Docs drift fix: `ARCHITECTURE.md`, `MEMORY-LIFECYCLE.md`, `CONFIG.md`, `MCP-MULTI-PROJECT.md`, `FILE-MAP.md` bumped to v1.6.x; MCP protocol-version lists aligned; `CLI.md`/`README.md` document the new `trust`/`security_flags`/`evidence_state` fields.

### ADRs
- ADR-015 — Retrieved memory is untrusted evidence (trust boundary).
- ADR-016 — Evidence freshness is derived metadata, not persisted.

### Test / dependency status
- 249 tests pass (was 187); 5 skipped (symlinks on Windows).
- 0 required runtime dependencies (core stdlib-only; `sentence-transformers`/`numpy` optional).
- No retrieval-quality regression (memory-quality benchmark: R@1=63.64%, MRR=0.738, leak=0% — unchanged).

## 1.6.0 — 2026-08-25

Memory-quality benchmark, dual-era MCP 2026-07-28, tool schemas, adaptive retrieval, link-aware context, `consolidate --prepare`, router latency benchmark, client docs.

### Memory-quality benchmark (CEL A)
- `tests/memory_quality_benchmark.py` + `tests/fixtures/memory_corpus/` (33 memories): deterministic, zero-dependency benchmark exercising the REAL `_search_with_cfg` / `search_with_meta` pipeline (not bare bm25_search).
- Cases: exact identifiers, file paths, method/class names, paraphrase, PL, EN, mixed, superseded decisions, valid_from/valid_to, `search --at`, contradictions, failure→fix, gotchas, archived isolation, distractors, multi-memory, abstention.
- Metrics: Recall@1/3/5, MRR, abstention precision/recall/F1, temporal accuracy, superseded/archived leakage rate, p50/p95 latency, approximate context tokens. `--smoke` canary for CI.
- `confidence_kind: "heuristic"` added to abstention metadata (honest labeling — not a calibrated probability).

### MCP 2026-07-28 dual-era (CEL B)
- `server/discover` (no `initialize` required), per-request `_meta`, `resultType: "complete"`, modern response envelopes, `ttlMs`/`cacheScope`.
- Legacy (`2024-11-05`…`2025-11-25`) `initialize`/`notifications/initialized`/`tools/list`/`tools/call`/`ping`/`shutdown` unchanged.
- Shared `irag_mcp_protocol.py` (stdlib-only) centralizes version negotiation + envelopes for both `irag.py mcp` and `irag_mcp_router.py`.

### Better MCP schema (CEL C)
- Precise `inputSchema`: types, enums, `required`, `minimum` for `limit`, `additionalProperties: false` where safe.
- Tool `annotations`: `openWorldHint: false` (local memory), `readOnlyHint`/`destructiveHint`/`idempotentHint` per tool. `search`/`context` NOT idempotent (usage metadata side-effect).
- `outputSchema` + `structuredContent` for `search`, `status`, `tasks`, `projects`, `guard`.

### MCP search at + explain (CEL D)
- MCP `search` accepts `at` (temporal) and `explain`. Abstention metadata in `structuredContent`.

### Registry strict write (CEL E)
- `write` must be a JSON boolean (`true`/`false`); `"false"`, `0`, `1` → `RegistryError`. `root` must be a string; project id non-empty; default `write: false`.

### Sources in chunk prefix (CEL F)
- `sources`/`evidence` rendered into the lightweight chunk prefix (bounded: max 6 entries, 160 chars each) so file paths and symbol names are searchable via the sparse channel without aggressive stemming. Deterministic chunk IDs preserved; content hash invalidates the correct cache entry.

### Adaptive retrieval (CEL G)
- `retrieval.mode: adaptive` runs sparse first; invokes dense only if sparse evidence is weak/ambiguous (explicit heuristics: `min_top_score`, `margin`, `min_matched`). Opt-in, NOT default. Graceful sparse fallback when embeddings unavailable. Benchmark-gated: stays opt-in until a benchmark proves a quality gain or latency reduction.

### Bounded link-aware context (CEL H)
- `context` expands base results by 1 hop over `links`/`supersedes`/`derived_from`/`superseded_by` with a hard budget (`max_hops=1`, `max_neighbors_per_memory=2`, `max_linked_results=3`). Linked results carry provenance (`retrieval_reason: linked_from`), cannot resurrect archived/invalid, respect temporal validity, cycle-guarded. `search` unchanged by default.

### `consolidate --prepare` (CEL I)
- Deterministic JSON segment packet (objective, completed, decisions, failures/gotchas, changed files, checkpoint metadata). No LLM, no auto-write, no history deletion.

### Router latency benchmark (CEL J)
- `tests/router_latency_benchmark.py`: direct vs router, sparse. ~64ms mean overhead (subprocess startup) — below 100ms threshold → persistent child pool NOT warranted (ADR-014).

### Client docs (CEL K)
- `docs/MCP.md` rewritten: dual-era protocol, annotations, structured content, client config table, Windows/Linux examples, troubleshooting (server not found, cwd, Python executable, registry, write:false), JetBrains built-in MCP direction note.
- `examples/`: `projects.example.json`, `warp.example.json` (with `working_directory`), `jetbrains.example.json`, `opencode-v2.example.jsonc`, `opencode-legacy.example.json`. No non-standard top-level `notes` fields.

### MCP tests (CEL L)
- `tests/test_mcp_modern.py` (16 tests): `server/discover` (no-init), modern `tools/list` (resultType, deterministic order, annotations), modern `tools/call` (structuredContent, outputSchema), invalid version → error, legacy `initialize` regression, stdout purity, router modern + `structuredContent` passthrough, protocol helpers.
- CI `mcp-compat` job runs `test_mcp_modern` alongside `test_mcp_server`/`test_mcp_router` in the `mcp>=2,<3` venv.

### Docs & ADRs
- ADR-010 (dual-era MCP), ADR-011 (adaptive opt-in), ADR-012 (bounded links, no graph DB), ADR-013 (`consolidate --prepare` read-only), ADR-014 (router no pool yet).
- `docs/COMPATIBILITY.md` updated for 2026-07-28.

## 1.5.0 — 2026-08-25

Retrieval correctness, abstention, FTS5 acceleration, multi-project MCP, and CI.

### Relevance / abstention gate (B)
- Retrieval now separates **raw evidence** from policy ranking. A relevance/admission gate runs before any policy boost: policy can only rank admitted candidates, never rescue an irrelevant one.
- `search --json --meta` wraps results with `abstained`, `retrieval_confidence` (calibrated 0–1, not a probability), `reason`, `admitted`, `rejected`, `rejected_detail`. Plain `--json` is unchanged (bare list) for backward compatibility.
- `search_with_meta()` returns `(results, meta)`; per-candidate `explain` carries `admission` / `admission_reason`.
- Config: `retrieval.abstention.{enabled, require_sparse_match, min_dense_score}`.
- Tests: `tests/test_admission_gate.py` (per-mode gate decisions + abstention metadata).

### FTS5 candidate prefilter (C)
- Optional accelerator: FTS5 top-n **∪** Python BM25 top-k narrows the scoring pool without changing the ranking and never drops a hit the full scan returns.
- Automatic fallback to the full scan when the index is missing/stale (any memory newer than the index), FTS5 is unavailable, the corpus is below `min_corpus_size`, or FTS5 matches nothing.
- Config: `retrieval.fts_prefilter.{enabled, min_corpus_size}`.
- Tests: `tests/test_fts_prefilter.py` (parity enabled/disabled, stale-index fallback, tiny-corpus skip, no-index fallback).

### Multi-project MCP router (E)
- New `irag_mcp_router.py`: one MCP stdio server in front of many projects.
- Registry JSON allowlist (`projects.<id>.{root, write}`); only registered ids are routable.
- `write:false` blocks mutating tools (`remember`, `checkpoint`, `resume`) before any subprocess is spawned.
- Isolation: every call runs in a fresh `irag.py mcp` subprocess with `cwd=<project root>` — no cross-project state.
- `projects` tool reports id / root / write / availability. See `docs/MCP-MULTI-PROJECT.md` and `examples/projects.example.json`.
- Tests: `tests/test_mcp_router.py` (registry, unknown-project rejection, read-only enforcement, cross-project isolation, protocol/stdout purity).

### MCP protocol hardening (D)
- Pure-stdout JSON-RPC 2.0 (protocol only on stdout; logs on stderr).
- `initialize` version negotiation: `2025-11-25` / `2025-06-18` / `2025-03-26` / `2024-11-05` (client's version when supported, else latest); `ping`, deterministic `tools/list`; legacy `notifications/initialized` / `shutdown` still handled.
- Verified against the official `mcp` Python SDK client (`mcp>=2,<3`) — `tests/test_mcp_sdk_compat.py` (skipped when the optional SDK is absent).
- `tests/test_mcp_server.py`: protocol, stdout purity, unknown-tool and parse-error handling, read-only `search`.

### Config correctness (A1–A2)
- Fingerprint cache correctness: the tracked working-tree/index diff is **always** hashed fresh — a cached fingerprint never hides an uncommitted tracked change. Only the untracked-file digest is cached. Tests: `tests/test_fingerprint_cache.py`.
- Recursive `deep_merge` (overriding one leaf never drops sibling defaults) + deeper YAML-subset parser (block lists). Tests: `tests/test_config_merge.py`.
- `config --validate` covers `abstention` + `fts_prefilter`.

### CI (G)
- `.github/workflows/ci.yml` (replaces `self-test.yml`): tests matrix — Ubuntu py3.8 / py3.12, Windows py3.12 — compile gate, `self_test.py`, full `unittest` suite, retrieval benchmarks.
- Separate `mcp-compat` job: official `mcp` SDK in its own venv, running the SDK-handshake and protocol suites.

### Docs
- `docs/MCP-MULTI-PROJECT.md`, `docs/ADR.md`, README "What's new in 1.5.0", `docs/CONFIG.md` (abstention + FTS5), `docs/CLI.md` (`--meta`), `docs/COMPATIBILITY.md` (MCP SDK).
- Version bumped to **1.5.0** across `VERSION`, `irag.py`, `install.py`, `uninstall.py`, `pack.py`.

## 1.4.0 — 2026-08-24

Section-aware chunking, read-only search, SimHash dedup, multilingual profiles, temporal metadata.

### Section-aware chunking (task 5)
- `chunk_memory()`: splits by Markdown headings, prefix with title/type/tags/scope.
- Short memories (<threshold_chars) get exactly 1 chunk.
- Chunk ID: `<memory_id>:<section-slug>:<ordinal>`.
- Config: `retrieval.chunking.enabled/threshold_chars/target_chars/overlap_chars`.
- Schema v3 migration.

### Read-only search / migrate-usage (task 6)
- `_mark_accessed_db()` uses SQLite usage table — search/context no longer mutate Markdown.
- `migrate-usage --dry-run/--apply [--strip] [--json]` — migrate frontmatter last_accessed to DB.
  - `--apply` imports the historical date (does not fake a fresh access).
  - `--strip` backs up each stripped file to `INTERNAL_RAG/usage-backups/` before rewriting, and reports all changed files + backups.
- doctor: never-accessed, stale (config `usage.stale_days`, default 30), top-accessed from SQLite usage table. Missing usage store is reported as info, never an error.
- `index --rebuild` preserves usage rows by default; add `--reset-usage` to explicitly reset them.
- Incremental sync/upsert preserves existing usage rows (no reset on content update).
- `content_hash` excludes `last_accessed`/`access_count` — usage never invalidates embeddings.
- `access_count` does not influence ranking (no popularity bias without benchmark).
- Tests: search leaves mtime/hash of Markdown unchanged; usage count grows in DB; dry-run/apply/strip + backup; search works with DB unavailable; rebuild/sync preserve usage.

### SimHash deduplication (task 7)
- `_canonical_memory_text()`: title + Knowledge + Consequence + significant tags/scope; NFKD + casefold + whitespace-collapse normalization (PL diacritics & formatting differences do not break comparison); excludes created/updated/last_accessed/status.
- Exact fingerprint: SHA-256 of normalized canonical text.
- Near fingerprint: 64-bit SimHash over tokens (pure stdlib, no datasketch/MinHash); Hamming distance ≤ 3 = near duplicate.
- `remember`/`remember-batch`: exact match => blocked by default; near => warning; title-Jaccard remains an additional signal; `--force` bypasses.
- Conflict detection stays **separate** from duplicate detection (opposing decisions are conflicts, never duplicates).
- Archived memories: not active duplicates (no block), shown informationally in `near`.
- `remember --json` returns: `status`, `duplicate: {exact, near, title_similar, recommended_action: update|supersede|force|null}`, and a separate `conflict` list when applicable.
- `import` remains idempotent: second import of the same bundle is skipped without `--overwrite`.
- Algorithm + limitations documented in `docs/DEDUP.md`.
- Tests: `tests/test_dedup.py` (identical text different title, near rephrase, opposing decision, Polish/whitespace normalization, force bypass, archived informational, JSON shape, import idempotency).

### Multilingual PL/EN profile (task 8)
- `retrieval.profile: english-fast | multilingual` (default: english-fast — kept for existing users).
- english-fast: all-MiniLM-L6-v2, no query/passage prefix (per model card).
- multilingual: intfloat/multilingual-e5-small with `query: `/`passage: ` prefixes (per E5 model card + Sentence Transformers).
- In-memory embedding cache key includes model identity; persistent cache keyed by `(chunk_id, model_id, precision)` — profiles never share vectors.
- `embeddings-info` reports the active profile and resolved model.
- `retrieval.embeddings_model` (explicit) overrides the profile; explicit models are encoded without prefix.
- Sparse channel: no external stemmer; code identifiers preserved verbatim (`refresh_token_cache`, `AuthService.refresh()`, `src/auth/session.py`); conservative PL stopword list gated behind `retrieval.pl_stopwords` (default `true`, benchmark-justified); `retrieval.query_expansion: false` disables the English synonym compatibility layer.
- Benchmark (`tests/multilingual_benchmark.py`, 15 PL + 15 EN + 10 mixed queries, Recall@1/3/5 + MRR per group, report `tests/benchmark_multilingual.json`):
  - hybrid multilingual > hybrid english-fast on the PL group (R@1 12.5%→18.75%, MRR 0.227→0.269), EN/MIXED not regressed → multilingual is the officially supported choice for PL/EN projects, **not** the default.
  - dense hybrid adds little over sparse on the small fixture corpus and costs latency — re-run the benchmark on your corpus before enabling hybrid.
  - PL stopwords: PL group R@1 62%→69%, MRR 0.690→0.721 → kept enabled by default.
- `pack.py --with-embeddings --profile english-fast|multilingual` (or `--model` to pin an explicit model).

### Temporal, safe knowledge lifecycle (task 9)
- Optional schema-2 lifecycle frontmatter fields (all backward-compatible — schema-1 memories work unchanged): `confidence: high|medium|low`, `valid_from`, `valid_to`, `supersedes: []`, `derived_from: []`.
- `remember`/`remember-batch`/`update` accept and write the lifecycle fields; `validate` rejects invalid `confidence` values and malformed dates (`valid_from`/`valid_to`/`created`).
- `supersede <ref> --by <new>` (never deletes history): sets `status: superseded`, closes the validity window (`valid_to`, default today or `--valid-to`), records `superseded_by`, and adds `supersedes: [old-id]` to the replacement. `--force` records the `--by` reference even if the replacement does not exist yet.
- `timeline` sorts by **effective validity** (`valid_from` else `created`), oldest first — not by filename or `created` alone.
- `search --at YYYY-MM-DD` (temporal): keeps superseded memories whose window covered the date (history queries), excludes memories not yet valid; post-filter enforces `valid_from ≤ D ≤ valid_to`; malformed dates are ignored, no error. `_policy_boost` lifts date-valid superseded memories (+0.5) instead of penalizing them (-4.0).
- `context` defaults to current active memory but adds a read-only **HISTORY & CONFLICTS** section (superseded/invalid/archived related to the task, with `superseded_by`, validity window, cross-link to the replacement when both are in the result set); `search --json` exposes the same as a `history` block per affected result.
- `consolidate --dry-run [--json]` — deterministic, read-only report (never deletes, never rewrites, no LLM summarization): exact/near duplicates, superseded entries (with `superseded_by`/`valid_to`), archived entries, never-accessed old entries (`--never-accessed-days`, default 90), old session snapshots (`--snapshot-age-days`, default 30), and potentially conflicting active memories (same type + overlapping scope + ≥40% body-token overlap). `--json` also emits a `plan` array of recommended actions for an OpenCode agent to evaluate — `consolidate` itself never executes them.
- `update` never removes history (frontmatter changes + dated `## Update` appends only).
- Tests: `tests/test_lifecycle.py` (10 tests): A→B preserves A historically; `--at` before the change finds A / after prefers B; unknown dates do not raise; schema-1 import still works; `consolidate --dry-run` is deterministic and read-only (identical JSON across runs, zero file mutations); timeline sorts by effective validity; schema-2 fields round-trip through `remember`; `validate` rejects bad confidence/dates.

## 1.3.0 — 2026-08-24

Persistent embedding cache in SQLite.

### Embedding cache table (schema v2)
- New `embeddings` table in `.index.sqlite3`: `chunk_id`, `model_id`, `model_revision`, `dimension`, `precision`, `content_hash`, `vector` (BLOB), `created_at`.
- Migration v1→v2 via `PRAGMA user_version`.
- BLOB format: float32, little-endian, raw bytes (deterministic byte order + dtype).
- Primary key: `(chunk_id, model_id, precision)` — multiple models coexist.

### Cache rules
1. Same `content_hash` + `model_id` + `precision` → no re-encode.
2. Changed content → only that chunk's embedding is invalidated.
3. `last_accessed`/`access_count` changes → no embedding invalidation.
4. Model change → new cache series, old cache preserved.
5. `index --vacuum` cleans stale embedding entries + detects corrupt BLOBs.
6. Query embedding stays in-memory; corpus embeddings are persistent.
7. No `sqlite-vec` required — exact similarity via NumPy on BLOB read.
8. If NumPy/sentence-transformers unavailable → sparse-only, no error.

### Integration
- `irag_embeddings.py` `dense_search_raw()` now checks persistent cache first.
  Only missing/stale chunks are encoded; results stored back to SQLite.
- In-process `_EMBED_CACHE` remains as L2 (session-level) cache.
- `irag.py index --embed-missing` — show missing/stale embeddings for configured model.
- `irag.py embeddings-info` — reports model, dimension, precision, cached/missing chunks, disk bytes.
- `irag.py index --vacuum` — also cleans stale embeddings + reports corrupt vectors.

### Tests
- `tests/test_sqlite_index.py` — 29 tests (was 19): added embedding cache tests with mock encoder.
  - set/get embedding, content hash mismatch, usage metadata isolation, model change,
    corrupt vector detection, batch retrieval, status, cleanup, first/second process,
    single chunk re-encode.
- Total: 73 tests (44 retrieval + 29 SQLite index), all pass with zero dependencies.

## 1.2.0 — 2026-08-24

Optional SQLite FTS5 index for retrieval acceleration.

### SQLite index (`irag_index.py`)
- New module `irag_index.py` — optional, zero-dependency (uses `sqlite3` from stdlib).
- Location: `INTERNAL_RAG/.index.sqlite3` (cache only — Markdown remains source of truth).
- Schema v1: `documents`, `chunks`, `usage` tables (+ optional `fts5_memories` virtual table).
- Migrations via `PRAGMA user_version`; newer schema produces clear error.
- FTS5 detection: if runtime sqlite3 lacks FTS5, graceful fallback to Python BM25.
- Content hash: SHA-256 of canonical content (excludes `last_accessed`/`access_count`).
- Changed hash → reindex document; deleted Markdown → remove from index.

### Index commands
- `irag.py index --rebuild` — full rebuild from Markdown.
- `irag.py index --status` — SQLite version, FTS5 available, schema, indexed count, stale/missing.
- `irag.py index --vacuum` — VACUUM the database.
- `irag.py index --status --json` — JSON output.

### Doctor
- Reports SQLite version, FTS5 availability, schema version, indexed memory count.
- Reports stale/missing documents with warning severity.

### Hybrid retrieval integration
- Sparse channel tries FTS5 first; if unavailable or no results, falls back to Python BM25.
- FTS5 uses `bm25()` with higher weights for title/tags/path than body.
- Fallback is transparent — same search results format, no error.

### Security
- All index operations use transactions.
- Index writes never modify Markdown files.
- `.index.sqlite3` excluded from Git (`.gitignore` + `.git/info/exclude`).
- `privacy_check.py` recognizes `.index.sqlite3` as managed local file.

### Tests
- `tests/test_sqlite_index.py` — 19 tests: rebuild, incremental add/update/delete, FTS5 search,
  type/status filters, content hash, schema version, newer schema error, vacuum, access tracking,
  delete+rebuild, search-does-not-mutate-markdown.
- Total: 63 tests (44 retrieval + 19 SQLite index), all pass with zero dependencies.

## 1.1.0 — 2026-08-24

Hybrid retrieval with Reciprocal Rank Fusion.

### Hybrid retrieval pipeline
- BM25 sparse retrieval is **always** executed.
- Dense embeddings retrieval is executed when `mode: hybrid` (default) and encoder is available.
- If dense fails, graceful degradation to sparse-only — no error.
- **Reciprocal Rank Fusion (RRF)** combines channels:
  `fused(doc) = sparse_weight/(rrf_k + sparse_rank) + dense_weight/(rrf_k + dense_rank)`
- MMR reranking runs **after** fusion, using dense cosine similarity for diversity when available, token-Jaccard fallback otherwise.

### New config options
```yaml
retrieval:
  mode: hybrid           # sparse | dense | hybrid
  rrf_k: 60              # RRF smoothing constant
  sparse_weight: 1.0     # RRF weight for BM25 channel
  dense_weight: 1.0      # RRF weight for dense channel
  candidate_multiplier: 4  # over-fetch factor for candidate pool
```
- `retrieval.embeddings` (old) remains compatible — mapped to mode behavior.
- Existing `.irag.yml` files are not broken.

### `--explain` flag
- `search --json --explain` returns per-result breakdown:
  `sparse_score`, `sparse_rank`, `dense_score`, `dense_rank`, `rrf_score`, `policy_boost`, `final_score`, `final_rank`, `matched_tokens`, `retrieval_mode`.
- `search --json` (without `--explain`) preserves the existing JSON fields.

### Embeddings module
- New `dense_search_raw()` — returns raw (cosine_sim, idx) pairs without policy boosts.
- New `dense_similarity_matrix()` — for MMR diversity using cosine similarity.
- `embeddings_search()` (legacy) preserved for backward compatibility.

### Tests
- 44 tests (was 33): added RRF fusion, hybrid retrieval, explain output, filter-before-retrieval, determinism tests.
- All 44 tests pass with zero dependencies (sparse-only mode in test harness).

## 1.0.4 — 2026-08-24

Sparse retrieval fix and deterministic test suite.

### BM25 IDF fix
- Fixed IDF formula from `((N - df + 0.5) / (df + 0.5) + 1.0)` to standard `log(1 + (N - df + 0.5) / (df + 0.5))`.
- Uses `math.log` from standard library — no external dependency added.
- Extracted BM25 into testable functions: `bm25_idf()`, `bm25_term_score()`, `bm25_doc_score()`.
- `k1` and `b` are now configurable via `.irag.yml` (`retrieval.bm25_k1`, `retrieval.bm25_b`).
- Graceful behavior for empty query and empty corpus preserved.

### Deterministic test suite
- `tests/test_retrieval.py` — 33 unit tests (unittest, standard library only).
  - Rare term ranks correct document higher.
  - Exact symbol/function name searchable (e.g. `refresh_token_cache`).
  - Frequent term does not dominate ranking.
  - Active/tentative/superseded status semantics verified.
  - Type and status filters tested.
  - Polish characters in query and document do not break matching (NFKD normalization).
  - Results are deterministic for fixed fixtures.
- `tests/fixtures/retrieval/` — 22 memories: EN, PL, decisions, knowledge, gotchas, failures, hypotheses, distractors.
- `tests/retrieval_benchmark.py` — Recall@1/3/5, MRR, p50/p95 latency on synthetic corpora (100, 1000, 10000).

### self_test.py
- Added sparse retrieval smoke test.

## 1.0.3 — 2026-08-24

Quality and intelligence release.

### Recency boost (H1)
- BM25 and embeddings scoring now gives a small boost to recently created/updated memories (<7 days: +0.3 BM25, +0.03 embeddings; <30 days: +0.1/+0.01).

### Conflict detection (H2)
- `remember` now detects potential conflicts with active memories of the same type/scope (body token overlap >= 50%).
- Warns and suggests `supersede` instead. `--force` overrides.

### Plugin debounce (H3)
- OpenCode resilience plugin now debounces auto-checkpoints (min 60s between, counts skipped edits).

### Batch remember (H4)
- `remember-batch <file.json>` — create multiple memories from a JSON array.

### Clean command (H5)
- `clean [--force]` — permanently delete all files from `archive/` (forgotten memories).

### Config validation (H6)
- `config --validate` — checks config values (ranges, types, unknown sections).

### Memory access tracking (H7)
- `search` and `context` now write `last_accessed` to memory frontmatter.
- `doctor` reports how many memories have never been accessed (archive candidates).

## 1.0.2 — 2026-08-24

Quality and reliability release.

### Token budget enforcement (G1)
- `context` now sorts results by score and cuts memories to fit `tokens.context_budget`.
- Reports `dropped=N` when memories are excluded for budget.

### Stale memory detection (G2)
- `validate` now checks `sources:` (evidence) paths and warns if they no longer exist.
- Non-blocking warning (exit 0 unless there are errors).

### Duplicate detection (G3)
- `remember` checks for similar existing memories (Jaccard title similarity >= 0.7).
- Warns and suggests `update` instead. `--force` overrides.

### Privacy scan at write-time (G4)
- `remember` scans `body`, `title`, `evidence`, `consequence` for secret patterns.
- Refuses to write if secrets detected. `--allow-secret` bypasses (use with caution).

### Auto-checkpoint timer (G5)
- `checkpoints.max_age_minutes` config (default 0 = disabled).
- `guard` and `context` warn (non-blocking) if last checkpoint exceeds the age threshold.

### Recent git log in context (G6)
- `context` now includes a `## RECENT COMMITS` section (last 5 commits).
- Helps recovery by showing what was recently committed.

### Offline / air-gapped support
- `pack.py` — creates a self-contained ZIP with wheels + pre-downloaded model.
- `irag_embeddings.py` supports local model paths (via `IRAG_EMBED_MODEL` or config).
- New `docs/OFFLINE.md` — full guide for air-gapped installation.
- Zero-dependency core (BM25+MMR) works fully offline without any pip install.

## 1.0.1 — 2026-08-24

Patch release: full English documentation and professionalization.

### Documentation
- All documentation translated to English (README, docs/*, INSTALL, START_HERE, CONTRIBUTING, SECURITY, RELEASE_CHECKLIST, INTERNAL_RAG/README).
- New docs: `docs/CLI.md` (full command reference), `docs/GIT-HOOKS.md`.
- README badges (version, license, Python).

### Functional fixes
- `search --json` now returns `matched_tokens` for each result.
- `remember --links` stored in frontmatter `links:` field (not just body).
- MCP server handles `notifications/initialized` and `shutdown` methods.
- `compact` preserves section structure; trims long lists (not the whole section).
- `privacy_check.py` now audits `.irag.yml` (managed path detection).
- Added `requirements-optional.txt` for embeddings.
- `.gitignore` now covers `.tasks.json`, `.fpcache.json`, `exports/`.
- CI workflow note in docs (token `workflow` scope required to push `.github/workflows/`).

### CLI professionalization
- Global `--quiet` and `--verbose` flags.
- `search --limit` defaults to config `retrieval.limit` (was 0→8, unintuitive).
- `history` command: list checkpoint history (from rolling log).
- `forget-task <id>`: drop a specific task by index/id (not just clear-all).
- `resume` now updates WORKING_STATE sections (Current request, phase, next).
- `config --init`: writes a `.irag.yml` template.
- `--embeddings on|off|auto` CLI override (per-invocation).
- `show --section <name>`: extract a single section from a memory.
- Schema versioning in `.checkpoint.json` and `.tasks.json` (`schema: 2`).
- `self_test.py` extended with CRUD, MCP, and hooks smoke tests.

## 1.0.0 — 2026-08-24

First stable release. Full professional RAG for terminal coding agents.

### Retrieval
- BM25 + MMR scoring with stopwords and light stemming (zero-dep).
- Optional sentence-transformers embeddings via `irag_embeddings.py` (graceful BM25 fallback).
- `--json` output for `search`, `context`, `status`, `diff`, `timeline`, `tasks`, `resume`, `doctor`.
- Token estimation in `context` packet (working_state, memories, budget).
- `.irag.yml` config: `retrieval.limit`, `mmr_lambda`, `min_score`, `embeddings`, `embeddings_model`.

### Memory CRUD
- `show <ref>` — read by path, basename, or id.
- `update <ref>` — status, verified, add/remove tags, append section.
- `supersede <ref> --by --reason` — mark replaced.
- `forget <ref>` — archive (not delete).
- `link --from --to` — cross-reference memories.
- `status` — counts by type/status + checkpoint freshness.
- `diff` — project changes since last checkpoint.
- `timeline` — memories by created date.

### Multi-task stack
- `push --task --reason` — stack the current task (with WORKING_STATE snapshot).
- `tasks` — show stack.
- `resume` — pop and restore WORKING_STATE, report fingerprint freshness.
- `forget-task` — clear stack.
- `compact` — archive and trim WORKING_STATE before context compaction.

### MCP server
- `irag.py mcp` — minimal JSON-RPC stdio server exposing context/search/checkpoint/guard/remember/status/tasks/resume.
- Compatible with Claude Code / Cursor / any MCP client.

### Git hooks (optional)
- `irag_hooks.py install|uninstall|status` — post-commit auto-checkpoint, post-checkout fingerprint invalidation, pre-push stale warning.
- Hooks never block git operations.

### Diagnostics & transfer
- `doctor` — health check (git, dirs, checkpoint, python, embeddings, config).
- `embeddings-info` — retrieval engine status.
- `export` / `import <file> [--overwrite]` — JSON bundle of memories + working state.
- `config` — show effective configuration.

### Integrations
- New OpenCode tools: `memory-remember`, `memory-status` (in addition to search/context/checkpoint/guard).
- `memory-search`, `memory-context`, `memory-checkpoint` now accept `--json` and richer args.
- Resilience plugin now calls `compact` before compaction.
- SKILL.md and AGENTS.md updated with full v1.0 command surface.
- Install/uninstall/privacy_check updated for new tool files and `.irag.yml`.

### Other
- Session snapshots archived to `INTERNAL_RAG/sessions/.snapshots/` (excluded from memory scan & validate).
- Fingerprint cache (`INTERNAL_RAG/.fpcache.json`) speeds up repeated `context`/`guard` calls; invalidated on checkout.
- `self_test.py` extended to cover v1.0 invariants.

## 0.4.0 — 2026-08-22
- GitHub documentation,
- improved PowerShell launchers,
- local-only via `.git/info/exclude`,
- `privacy_check.py`,
- `uninstall.py` with backup,
- local manifest in `.git`,
- self-test and GitHub Actions.

## 0.3.0 — 2026-08-22
- recovery detection,
- resilient checkpoints,
- guard,
- OpenCode auto-checkpoints.