# Changelog

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

### Temporal metadata + consolidate (task 9)
- Frontmatter: `schema:2`, `valid_from`, `valid_to`, `confidence`, `supersedes`, `derived_from`.
- `supersede`: sets `valid_to`, `superseded_by`; new entry gets `supersedes`.
- `timeline`: sorts by effective validity (valid_from/created).
- `search --at YYYY-MM-DD`: filter memories valid at date.
- `consolidate --dry-run --json`: duplicates, superseded, archived, never-accessed, old snapshots, conflicts.
- Schema 1 memories still work (backward compatible).

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