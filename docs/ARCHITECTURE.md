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
- Default: BM25 (k1=1.5, b=0.75) with MMR (lambda from config).
- Optional: sentence-transformers (`irag_embeddings.py`), lazy-loaded, fallback to BM25.
- Stopwords, light stemming, status weighting (active/tentative/superseded/invalid).
- `--embeddings on|off|auto` CLI override.

### Lifecycle
- `context` compares the fingerprint with the last checkpoint → `RECOVERY REQUIRED` or fresh.
- `checkpoint` saves semantic state + fingerprint.
- `guard` detects changes after the last checkpoint.
- `compact` archives and trims WORKING_STATE (preserves section structure).
- `push`/`resume` task stack with state snapshot.
- `remember`/`show`/`update`/`supersede`/`forget`/`link` — durable memory CRUD.
- `export`/`import` — JSON transfer between projects.

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