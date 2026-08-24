# Architecture (v1.0.1)

```text
Warp / OpenCode / Claude Code / Cursor
      │
      ├── AGENTS.md
      ├── SKILL.md
      └── .irag.yml (optional)
               │
               ▼
            irag.py  (CLI, zero-dep core)
       ┌───────┼─────────┬───────────┬──────────┐
       │       │         │           │          │
    context  checkpoint  search    remember    tasks
       │       │         │           │          │
       └───────┼─────────┴───────────┴──────────┘
               ▼
         INTERNAL_RAG/
       (WORKING_STATE, decisions, knowledge,
        gotchas, failures, hypotheses, sessions, archive)
```

### Core (zero dependencies)
- `irag.py` — all CLI commands.
- `WORKING_STATE.md` — write-ahead checkpoint.
- `.checkpoint.json` — fingerprint + last checkpoint metadata (schema-versioned).
- `.tasks.json` — task stack (push/resume) (schema-versioned).
- `.fpcache.json` — fingerprint cache (invalidated on checkout).

### Retrieval
- **Hybrid pipeline**: BM25 sparse (always) + optional dense embeddings → Reciprocal Rank Fusion → MMR.
- **Section-aware chunking**: memories are split by Markdown headings into chunks.
  - Short memories (<threshold_chars) get exactly 1 chunk.
  - Long memories split by `##` headings; overlong sections further split with overlap.
  - Chunk prefix: title, type, tags, scope (lightweight, for retrieval context).
  - Chunk ID: `<memory_id>:<section-slug>:<ordinal>` (deterministic).
  - Config: `retrieval.chunking.enabled/threshold_chars/target_chars/overlap_chars`.
- **Chunk-level retrieval**: BM25/dense operate on chunks; results merged by `memory_id` after RRF.
  - Parent score = best chunk score (max).
  - Snippet from best-matching chunk.
  - Final top-k deduplicated by parent memory (no memory appears twice).
  - `--explain` returns `chunk_id`, `section`, `parent_memory_id`.
- **MMR on parent memories** (not chunks): 5 chunks of one document cannot displace 5 different relevant memories.
- **SQLite FTS5 index** (optional, zero-dep): `INTERNAL_RAG/.index.sqlite3` caches documents for fast FTS5 search.
  - If FTS5 available: uses SQLite `bm25()` with higher weights for title/tags/path.
  - If FTS5 unavailable: graceful fallback to pure-Python BM25 (same results, no error).
  - Markdown files remain the single source of truth; index is rebuildable cache.
- **Persistent embedding cache** (schema v2): corpus embeddings stored as float32 BLOBs in SQLite.
  - Only changed chunks are re-encoded; unchanged chunks use cached vectors.
  - Multiple models coexist; model change creates new cache series.
  - No `sqlite-vec` required — exact similarity via NumPy on BLOB read.
- BM25 with standard IDF `log(1 + (N - df + 0.5) / (df + 0.5))` (k1=1.5, b=0.75, configurable).
- Dense: sentence-transformers (`irag_embeddings.py`), lazy-loaded, graceful fallback to sparse-only.
- **RRF**: `fused(doc) = sparse_weight/(rrf_k + sparse_rank) + dense_weight/(rrf_k + dense_rank)`.
- MMR reranking after fusion — uses dense cosine similarity for diversity when available, token-Jaccard fallback.
- Policy boosts (status, type priority, recency) applied after fusion.
- **Temporal retrieval** (`search --at YYYY-MM-DD`): candidate filter keeps superseded memories whose validity window covered the target date; `_policy_boost` lifts them (+0.5) so history stays retrievable while `invalid`/`archived` remain excluded; a post-retrieval validity-window filter enforces `valid_from ≤ D ≤ valid_to`. Malformed dates are ignored, never an error.
- Stopwords, light stemming, query expansion with synonyms.
- `--type` and `--status` filters applied before retrieval.
- `--embeddings on|off|auto` CLI override. `--explain` for per-channel scoring breakdown.
- `context` output groups memories: Verified facts, Lessons & pitfalls, Unverified hypotheses; plus a read-only **HISTORY & CONFLICTS** section for superseded/invalid/archived results tied to the task.
- Deterministic test suite: `tests/test_retrieval.py` (44 tests), `tests/test_sqlite_index.py` (19 tests), `tests/test_lifecycle.py` (10 tests), `tests/retrieval_benchmark.py`.

### Lifecycle
- `context` compares the fingerprint with the last checkpoint → `RECOVERY REQUIRED` or fresh.
- `checkpoint` saves semantic state + fingerprint.
- `guard` detects changes after the last checkpoint.
- `compact` archives and trims WORKING_STATE (preserves section structure).
- `push`/`resume` task stack with state snapshot.
- `remember`/`show`/`update`/`supersede`/`forget`/`link` — durable memory CRUD.
- **Schema-2 temporal fields** (optional, schema-1 compatible): `confidence` (high|medium|low), `valid_from`, `valid_to`, `supersedes[]`, `derived_from[]`. Written by `remember`/`update`/`supersede`; validated by `validate`; consumed by `search --at`, `timeline`, `_temporal_explain`.
- **Supersession**: `supersede <ref> --by <new>` marks the old memory `superseded`, closes its validity window (`valid_to`), records `superseded_by`, and adds `supersedes: [old-id]` to the replacement. The old memory is **never deleted** — it remains readable, searchable via `--at`, and present in `timeline`.
- `timeline` sorts by effective validity (`valid_from` else `created`), oldest first.
- `consolidate --dry-run [--json]` — deterministic read-only audit (duplicates, superseded, archived, never-accessed old, old snapshots, conflicting active) with a `plan` for the agent. No deletion, no rewrite, no LLM summarization.
- `export`/`import` — JSON transfer between projects (schema-1 bundles import without change).

### Integrations
- OpenCode: tools (`memory-*`), plugin (auto-checkpoint + compact), commands (`/memory*`, `/checkpoint`).
- Warp: `AGENTS.md` + skill.
- MCP: `irag.py mcp` (JSON-RPC stdio).
- Git hooks (optional): post-commit auto-checkpoint, post-checkout invalidate, pre-push warn.

### Privacy
- Default local-only via `.git/info/exclude`.
- `privacy_check.py` audits tracked files, secret patterns, git history, and `.irag.yml`.
- `INTERNAL_RAG/` and tools should never be committed (unless `--share-tools`).

Durable memory from `decisions`, `knowledge`, `gotchas`, `failures`, `hypotheses` is loaded selectively via retrieval, never in bulk.