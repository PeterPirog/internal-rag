# Changelog

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
- dokumentacja GitHub,
- poprawione launchery PowerShell,
- local-only przez `.git/info/exclude`,
- `privacy_check.py`,
- `uninstall.py` z backupem,
- lokalny manifest w `.git`,
- self-test i GitHub Actions.

## 0.3.0 — 2026-08-22
- recovery detection,
- resilient checkpoints,
- guard,
- OpenCode auto-checkpoints.