# CLI reference (v1.0.1)

All commands are invoked as `irag.py <command> [options]`. Use `python` on Windows and `python3` on Linux/macOS.

## Global flags

| Flag | Description |
|------|-------------|
| `--version` | Print version and exit. |
| `--quiet` | Suppress non-essential output (errors only). |
| `--verbose` | Show extra detail (e.g. matched tokens, full paths). |
| `--embeddings on\|off\|auto` | Override retrieval engine for this invocation. |

## Commands

### `init`
Initialize the `INTERNAL_RAG/` skeleton. Idempotent.

### `context --task "<task>" [--limit N] [--json] [--type T1 T2 ...] [--status S1 S2 ...]`
Start or resume a task. Compares the project fingerprint with the last checkpoint. Returns a context packet with memories **grouped by type**: Verified facts (decisions/knowledge/constraints), Lessons & pitfalls (gotchas/failures), Unverified hypotheses. `--type` and `--status` filter candidates. Query is auto-expanded with synonyms. `--json` for structured output.

### `checkpoint [--reason R] [--task T] [--objective O] [--phase P] [--completed C] [--in-progress I] [--blockers B] [--decisions D] [--next N] [--memory M] [--json]`
Persist the current operational state. Saves a fingerprint. Auto-archives a session snapshot when `checkpoints.auto_archive_sessions` is true.

### `guard`
Verify no project-code changes are missing from the last checkpoint. Exit code 0 = `GUARD OK`, 2 = `GUARD STALE`.

### `search --query "<q>" [--limit N] [--json] [--explain] [--embeddings on|off|auto] [--type T1 T2 ...] [--status S1 S2 ...]`
Search durable memories via hybrid retrieval (BM25 + optional dense → RRF → MMR). `--json` returns `path`, `score`, `type`, `status`, `snippet`, `matched_tokens`. `--explain` adds per-channel breakdown: `sparse_score`, `sparse_rank`, `dense_score`, `dense_rank`, `rrf_score`, `policy_boost`, `final_score`, `retrieval_mode`. `--type` filters by memory type(s). `--status` filters by status(es). Query is auto-expanded with synonyms.

### `remember --type T --title "..." --body "..." [--status S] [--scope SC] [--tags T1,T2] [--evidence E] [--consequence C] [--links L1,L2] [--force] [--allow-secret]`
Create a durable memory. Types: `decision`, `knowledge`, `constraint`, `gotcha`, `failure`, `hypothesis`, `session`. `--links` is stored in frontmatter. `--force` overrides duplicate and conflict detection. `--allow-secret` bypasses the secret-pattern scan (use with caution).

### `remember-batch <file.json>`
Create multiple memories from a JSON array. Each element needs `type`, `title`, `body` (optional: `status`, `scope`, `tags`, `evidence`, `consequence`, `links`). Duplicates are forced.

### `clean [--force]`
Permanently delete all files from `INTERNAL_RAG/archive/` (forgotten memories). `--force` confirms deletion.

### `show <ref> [--section NAME] [--json]`
Read a memory by path, basename, or id. `--section` extracts one section (e.g. `Knowledge`, `Consequence`, `Links`).

### `update <ref> [--status S] [--verified DATE] [--add-tags T] [--remove-tags T] [--append "..."]`
Update a memory's frontmatter and/or append a dated section. Use `--status active` to promote a hypothesis to verified knowledge.

### `supersede <ref> [--by <new-ref>] [--reason "..."]`
Mark a memory as superseded. Records `superseded_by`, `superseded_at`, `supersede_reason` in frontmatter.

### `forget <ref>`
Archive a memory (moves to `INTERNAL_RAG/archive/`). Does not delete.

### `link --from <ref> --to <ref>`
Add a cross-reference in the `from` memory's frontmatter `links:` field.

### `status [--json]`
Overview: memory counts by type/status, checkpoint freshness, branch, HEAD.

### `diff [--json]`
Show project-code changes since the last checkpoint.

### `timeline [--limit N] [--json]`
List memories by created date (newest first).

### `history [--json]`
List checkpoint history (reason, at, head, fingerprint prefix).

### `index [--rebuild] [--reset-usage] [--status] [--vacuum] [--embed-missing] [--json]`
Rebuild `INDEX.md` (default). `--rebuild` also rebuilds the SQLite FTS5 index from Markdown. Usage rows are **preserved** across rebuilds by default; pass `--reset-usage` to explicitly reset them. `--status` shows SQLite version, FTS5 availability, schema version, indexed count, stale/missing. `--vacuum` reclaims space and cleans stale embeddings. `--embed-missing` shows missing/stale embeddings for the configured model.

### `migrate-usage --dry-run | --apply [--strip] [--json]`
Migrate `last_accessed` from Markdown frontmatter to the SQLite usage store.
- `--dry-run` — report entries that would be imported (no writes).
- `--apply` — import the historical date into the usage table (does not fake a fresh access).
- `--strip` — also remove `last_accessed` from Markdown; each stripped file is first backed up to `INTERNAL_RAG/usage-backups/`, and all changed files/backups are reported.
- `--json` — machine-readable report.

### `validate`
Validate all memory frontmatter (required fields, allowed types/status) and check evidence paths still exist. Exit 1 on errors, 0 on success (warnings do not fail).

### `push --task "<task>" [--reason R]`
Push the current task onto the stack (with WORKING_STATE snapshot).

### `tasks [--json]`
Show the task stack.

### `resume [--discard-state] [--json]`
Pop the top task and restore its WORKING_STATE. Reports whether the project fingerprint still matches.

### `forget-task [<id>]`
Drop a specific task by 1-based index. Without `<id>`, clears the whole stack.

### `compact`
Archive the current WORKING_STATE to `sessions/.snapshots/` and trim long lists (preserves section structure).

### `doctor [--json]`
Health check: git, dirs, checkpoint freshness, python version, embeddings, config validation, never-accessed memories.

### `embeddings-info [--json]`
Show the retrieval engine status (configured, available, engine, plugin path).

### `config [--json] [--init] [--validate]`
Show the effective configuration. `--init` writes a `.irag.yml` template. `--validate` checks config values and reports issues.

### `export`
Export all memories + WORKING_STATE to `INTERNAL_RAG/exports/irag-export-<timestamp>.json`.

### `import <file> [--overwrite]`
Import memories from a JSON bundle. Skips existing files unless `--overwrite`.

### `mcp`
Run the MCP JSON-RPC stdio server. See `docs/MCP.md`.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error / validation error |
| 2 | Guard stale / doctor critical issue |
| 3 | Privacy check critical |