# Changelog

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