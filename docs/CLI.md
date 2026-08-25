# CLI reference (v1.7.0)

All commands are invoked as `mlm.py <command> [options]` (primary alias) or `irag.py <command> [options]` (legacy alias, still supported). Use `python` on Windows and `python3` on Linux/macOS.

> **Rebrand note:** The primary CLI is now `mlm` (`mlm.py`). The legacy `irag.py` module filename is kept for backward compatibility with existing installs, scripts, and stored data — both entrypoints run the same core.

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
Start or resume a task. Compares the project fingerprint with the last checkpoint. Returns a context packet with memories **grouped by type**: Verified facts (decisions/knowledge/constraints), Lessons & pitfalls (gotchas/failures), Unverified hypotheses. `--type` and `--status` filter candidates. Query is auto-expanded with synonyms. `--json` for structured output (carries `trust: "untrusted"` and per-memory `security_flags`). The text packet prints a `SECURITY NOTICE` header and delimits each memory with `=== BEGIN/END INTERNAL_RAG MEMORY ===`.

### `checkpoint [--reason R] [--task T] [--objective O] [--phase P] [--completed C] [--in-progress I] [--blockers B] [--decisions D] [--next N] [--memory M] [--json]`
Persist the current operational state. Saves a fingerprint. Auto-archives a session snapshot when `checkpoints.auto_archive_sessions` is true.

### `guard`
Verify no project-code changes are missing from the last checkpoint. Exit code 0 = `GUARD OK`, 2 = `GUARD STALE`.

### `search --query "<q>" [--limit N] [--json] [--explain] [--meta] [--embeddings on|off|auto] [--type T1 T2 ...] [--status S1 S2 ...] [--at YYYY-MM-DD]`
Search durable memories via hybrid retrieval (BM25 + optional dense → RRF → MMR). `--json` returns `path`, `score`, `type`, `status`, `snippet`, `matched_tokens`, `trust` (always `"untrusted"`), `security_flags` (optional), `evidence_state` (`present`/`missing`/`unverifiable`) and, when a result is superseded/invalid/archived, a read-only `history` block (`superseded_by`, `valid_from`, `valid_to`, `why`, `recommendation`, optional `conflict_with`). `--explain` adds per-channel breakdown: `sparse_score`, `sparse_rank`, `dense_score`, `dense_rank`, `rrf_score`, `policy_boost`, `final_score`, `retrieval_mode`. `--type` filters by memory type(s). `--status` filters by status(es). Query is auto-expanded with synonyms.

`--meta` (new in 1.5.0) wraps `--json` output with abstention metadata and the `trust` label. The bare list output of plain `--json` is unchanged (backward compatible):

```json
{
  "trust": "untrusted",
  "abstained": false,
  "retrieval_confidence": 0.4,
  "reason": "3 candidate(s) passed the relevance gate (1 rejected)",
  "admitted": 3,
  "rejected": 1,
  "rejected_detail": [{"memory_id": "mem-x", "reason": "sparse_no_token_match"}],
  "results": [ /* same items as plain --json; omitted for brevity */ ]
}
```

`abstained` is `true` when no candidate passed the relevance/admission gate; `retrieval_confidence` is a calibrated `0.0-1.0` evidence strength (not a probability), and `reason` is a human-readable explanation. This lets agents detect "no usable answer" instead of trusting a low-relevance hit.

`--at YYYY-MM-DD` (temporal) filters to memories whose validity window covers that date: `valid_from` (or `created`) ≤ date ≤ `valid_to` (if present). Superseded memories whose window covered that date remain retrievable for historical queries; active memories whose window has not started yet are excluded. Unknown/malformed dates are ignored (no error).

### `remember --type T --title "..." --body "..." [--status S] [--scope SC] [--tags T1,T2] [--evidence E] [--consequence C] [--links L1,L2] [--confidence high|medium|low] [--valid-from DATE] [--valid-to DATE] [--supersedes ID,ID] [--derived-from ID,ID] [--force] [--allow-secret] [--json]`
Create a durable memory. Types: `decision`, `knowledge`, `constraint`, `gotcha`, `failure`, `hypothesis`, `session`. `--links` is stored in frontmatter. Schema-2 optional lifecycle fields: `--confidence high|medium|low`, `--valid-from`/`--valid-to` (YYYY-MM-DD), `--supersedes` (comma-separated ids this replaces), `--derived-from` (comma-separated ids this was derived from). Exact/near duplicates are blocked by default (see `docs/DEDUP.md`); conflict detection is a separate signal recommending `supersede`. `--force` overrides duplicate and conflict detection. `--allow-secret` bypasses the secret-pattern scan (use with caution). `--json` returns `status` plus `duplicate: {exact, near, title_similar, recommended_action}` and, when applicable, a separate `conflict` list.

### `remember-batch <file.json>`
Create multiple memories from a JSON array. Each element needs `type`, `title`, `body` (optional: `status`, `scope`, `tags`, `evidence`, `consequence`, `links`, `force`). Duplicate detection runs per entry: exact/near duplicates are skipped (counted as skipped, not created); pass `force` in the entry or on the command line to override.

### `clean [--force]`
Permanently delete all files from `INTERNAL_RAG/archive/` (forgotten memories). `--force` confirms deletion.

### `show <ref> [--section NAME] [--json]`
Read a memory by path, basename, or id. `--section` extracts one section (e.g. `Knowledge`, `Consequence`, `Links`).

### `update <ref> [--status S] [--verified DATE] [--add-tags T] [--remove-tags T] [--append "..."] [--confidence C] [--valid-from DATE] [--valid-to DATE] [--supersedes ID,ID]`
Update a memory's frontmatter and/or append a dated section. Use `--status active` to promote a hypothesis to verified knowledge. Lifecycle fields can be set or cleared (pass empty `--valid-from`/`--valid-to` to clear). **History is never removed by update** — content sections are preserved, only frontmatter changes.

### `supersede <ref> [--by <new-ref>] [--reason "..."] [--valid-to DATE] [--force]`
Mark a memory as superseded (keeps full history — nothing is deleted):
- sets `status: superseded`;
- sets `valid_to` (default today, or `--valid-to` if provided);
- records `superseded_at`, `supersede_reason`, and `superseded_by: <new-id>` (when `--by` resolves to an existing memory);
- the replacement memory gains `supersedes: [<old-id>]`.
`--force` records the `--by` reference even if the replacement does not exist yet (create it first in most cases).

### `forget <ref>`
Archive a memory (moves to `INTERNAL_RAG/archive/`). Does not delete.

### `link --from <ref> --to <ref>`
Add a cross-reference in the `from` memory's frontmatter `links:` field.

### `status [--json]`
Overview: memory counts by type/status, checkpoint freshness, branch, HEAD.

### `diff [--json]`
Show project-code changes since the last checkpoint.

### `timeline [--limit N] [--json]`
List memories by **effective validity** (oldest first), then path. Effective validity = `valid_from` if present, otherwise `created`. `--json` items include `effective`, `created`, `valid_from`, `valid_to`, `type`, `status`, `title`, `path`.

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

### `consolidate --dry-run [--json] [--never-accessed-days N] [--snapshot-age-days N]`
Deterministic, **read-only** knowledge-consolidation report. `--dry-run` is the default and the only mode: it never deletes, never rewrites memories, and never summarizes via LLM. It reports:
- exact/near duplicates (SHA-256 + 64-bit SimHash, see `docs/DEDUP.md`);
- superseded entries (with `superseded_by` and `valid_to`);
- archived entries (under `archive/`);
- never-accessed entries older than `--never-accessed-days` (default 90);
- session snapshots older than `--snapshot-age-days` (default 30);
- potentially conflicting **active** memories (same type + overlapping scope + ≥40% body-token overlap).

`--json` also emits a `plan` array with deterministic recommended actions (e.g. `merge_or_supersede`, `resolve_conflicts`, `review_stale`) intended for an OpenCode agent to review and decide — `consolidate` itself never executes them.

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