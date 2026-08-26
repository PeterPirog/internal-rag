# Memory lifecycle (v1.8.0)

`WORKING_STATE.md` is short, frequently updated working memory (write-ahead checkpoint).

Store durable memory only for information useful in future sessions: decisions, constraints, root causes, gotchas, costly failed approaches, and hypotheses.

## What to store where

| Type | When to store | Default status |
|------|---------------|----------------|
| `decision` | A choice that affects future work (framework, library, architecture, pattern) | `active` |
| `knowledge` | A verified fact about the project (invariant, constraint, how something works) | `active` |
| `constraint` | A restriction that must be respected (API limits, compatibility, business rules) | `active` |
| `gotcha` | A non-obvious trap that cost time and could recur | `active` |
| `failure` | A failed approach that should not be repeated (with root cause) | `active` |
| `hypothesis` | An unverified idea or assumption — **not a fact** | `tentative` |
| `session` | A session summary (rarely needed; use checkpoints instead) | `active` |

## Statuses

- `active` — current, verified.
- `tentative` — hypothesis, unconfirmed (default for `hypothesis`).
- `superseded` — replaced by a newer one (`supersede --by`).
- `invalid` — wrong (`update --status invalid`).
- `archived` — forgotten (`forget` moves to `archive/`).

## Schema-2 lifecycle fields (optional, backward-compatible)

Schema-1 memories (no lifecycle fields) continue to work unchanged. Optional fields
(added via `remember --confidence/--valid-from/--valid-to/--supersedes/--derived-from`,
`update`, or `supersede`) enrich temporal management without requiring them:

| Field | Meaning |
|-------|---------|
| `confidence` | `high` \| `medium` \| `low` — how sure we are this memory is true. |
| `valid_from` | Date (YYYY-MM-DD) from which the memory is true. Falls back to `created` when absent. |
| `valid_to` | Date (YYYY-MM-DD) after which the memory stopped being true (set by `supersede`, or manually). |
| `supersedes` | List of ids this memory replaces (reverse link of `superseded_by`). |
| `derived_from` | List of ids this memory was derived from (provenance). |

`validate` rejects invalid `confidence` values and malformed dates in `valid_from`/`valid_to`/`created`.

## Temporal semantics

- **Effective validity** of a memory = `valid_from` (if present) else `created`.
- A memory is *valid at* date D when `valid_from ≤ D` and (no `valid_to` or `valid_to ≥ D`).
- `supersede <ref> --by <new>`:
  - sets `status: superseded` and `superseded_at`;
  - sets `valid_to` (default today, or `--valid-to`);
  - records `superseded_by: <new-id>` when `--by` resolves to an existing memory;
  - the replacement gains `supersedes: [<old-id>]`;
  - **the old memory is never deleted** — it stays readable, searchable (via `--at`), and in `timeline`.
- `search --at YYYY-MM-DD` filters results to memories valid at that date:
  - superseded memories whose window covered D remain retrievable (history queries);
  - memories not yet valid at D are excluded;
  - malformed dates are ignored, no error.
- `timeline` sorts by effective validity (oldest first), not by filename or `created` alone.
- `update` modifies frontmatter/append sections but **never deletes history**.

## Retrieval ranking

Memories are scored with **type-priority** so the most authoritative types surface first:
- `decision` (+0.8) > `knowledge` (+0.6) > `constraint` (+0.5) > `gotcha` (+0.4) > `failure` (+0.3) > `hypothesis` (+0.2) > `session` (+0.1)
- `active` status gets +1.0, `tentative` gets +0.6, `superseded` gets -4.0 — except with `search --at D`, a superseded memory whose validity window covered D gets +0.5 instead (history stays retrievable).
- `context` defaults to preferring current active memory, but includes a read-only **HISTORY & CONFLICTS** section listing superseded/invalid/archived results that relate to the task (with `superseded_by`, validity window, and cross-links when the replacement is also in the result set). `search --json` exposes the same as a `history` block per affected result.

The `context` packet groups results:
- **Verified facts** (decisions, knowledge, constraints) — trust as established context.
- **Lessons & pitfalls** (gotchas, failures) — apply to avoid repeating mistakes.
- **Unverified hypotheses** — treat as tentative, verify before acting.

`access_count` does **not** influence ranking (no popularity bias without a benchmark).

## Usage tracking (read-only)

Search/context are **logically read-only** against durable memory content:
- `last_accessed` / `access_count` live in the SQLite **usage store** (`.index.sqlite3`, `usage` table), never written back to Markdown during search.
- `content_hash` excludes usage fields, so usage tracking never invalidates embeddings.
- Missing usage store is not an error — search degrades to sparse-only and still succeeds.

Migration / housekeeping:
- `migrate-usage --dry-run` — report frontmatter `last_accessed` that would be imported.
- `migrate-usage --apply [--strip] [--json]` — import to DB; `--strip` removes the field from Markdown after creating a timestamped backup in `INTERNAL_RAG/usage-backups/`.
- `index --rebuild` preserves usage; `index --rebuild --reset-usage` explicitly resets it.
- `doctor` reports never-accessed and stale (config `usage.stale_days`, default 30) counts, plus top-accessed.

## CRUD

- `remember` — create (supports schema-2 lifecycle fields).
- `show` / `timeline` — read (`timeline` sorts by effective validity).
- `update` — modify (status, tags, append, lifecycle fields); never deletes history.
- `supersede` — mark replaced (sets validity window, links both directions).
- `forget` — archive (does not delete).
- `link` — cross-reference.
- `consolidate --dry-run [--json]` — deterministic read-only audit (duplicates, superseded, archived, never-accessed old, old snapshots, conflicting active) plus a `plan` for the agent to evaluate. Never deletes, never rewrites, never summarizes via LLM.

## Promote workflow

When a hypothesis is confirmed:
```bash
irag.py remember --type knowledge --title "Confirmed: X causes Y" --body "Verified by test Z."
irag.py supersede <hypothesis-ref> --by <new-knowledge-ref> --reason "confirmed in test Z"
```

When a hypothesis is disproven:
```bash
irag.py update <hypothesis-ref> --status invalid --append "Disproved by test Z."
```

## Consolidation (plan, not action)

`consolidate --dry-run --json` produces a deterministic, read-only report the agent can review:
`duplicates` (exact + near), `superseded`, `archived`, `never_accessed_old`, `old_snapshots`,
`conflicting_active`, and a `plan` array of recommended actions (`merge_or_supersede`,
`verify_links`, `review_archive`, `review_stale`, `review_snapshots`, `resolve_conflicts`).
It is a **planning aid only**: it does not mutate memory files, does not delete anything,
and has no LLM summarization. Applying any action is always an explicit, separate CLI step.

## Rules

A hypothesis is not a fact and should remain `tentative` until verified.

If memory contradicts current code/tests: trust the code, mark the old memory `superseded`/`invalid`, record new evidence, and rebuild the index (`irag.py index`).

Never store: passwords, tokens, keys, production data, full logs, full chain-of-thought.


## Ephemeral observations (v1.8.0)

Raw tool outputs (console, terminal, builds, lints, tests) do NOT automatically
become durable Markdown memory. They flow through an ephemeral layer first:

```
raw tool output -> ephemeral observation -> distillation -> admission -> durable conclusion -> raw observation deletion
```

### Ephemeral store (`irag_ephemeral.py`)

- SQLite-based, bounded storage (NOT durable Markdown; NOT indexed for retrieval)
- TTL-based expiry (default 30 minutes, configurable via `ephemeral.ttl_seconds`)
- `max_records` (200) and `max_bytes` (2MB) limits
- `max_record_bytes` (64KB) per observation
- Secret redaction (password=, api_key=, token=, etc. are replaced with [REDACTED])
- Promotion marks observation + deletes the raw content after durable memory is created
- Session-end cleanup via `clear_all()`

### Diagnostic distillation (`irag_distill.py`)

Stdlib-first extraction from large tool outputs (no LLM dependency):

- Extracts: command name, exit code, ERROR/WARNING/FAILED, exception type+message,
  stack frames (file:line:func), root cause, remediation, evidence excerpt, content hash
- `should_promote` only if confidence >= MEDIUM and root_cause/errors are present
- Successful output / warnings without future value -> `should_promote=False`
- 5000-line output -> short conclusion like "Test X fails because Y. Root cause in Z."

If the automatic conclusion is not confident enough, the observation remains
ephemeral and NO durable memory is created.

## Retention + GC (v1.8.0)

Non-aggressive lifecycle management. Never auto-deletes important knowledge.

### Retention classes

| Class | Description | GC behavior |
|---|---|---|
| `protected` | Active decisions, constraints | NEVER GC'd |
| `tentative_hypotheses` | Tentative hypotheses | Low priority, GC candidate after long disuse |
| `normal_durable` | Active knowledge, gotchas, failures | Standard retention |
| `archived` | Archived memories | Delete candidate after grace period |

### 4-stage decay

1. **Deprioritize** — reduce retrieval priority for unused low-value memories
2. **Archive candidate** — mark as GC/archive candidate after long disuse
3. **Archive** — move to `archive/` directory
4. **Delete** — physical removal only after additional grace period + explicit policy

Factors: created time, last accessed, access count, confidence, status, memory type,
evidence freshness, link/reference count, reinforcement/recent verification.

### CLI

```
mlm.py gc --dry-run          # safe default: report only
mlm.py gc --apply            # execute the plan
mlm.py gc --json             # machine-readable
mlm.py gc --grace-days N     # override grace period
```

**Decisions and constraints are NEVER deleted by decay alone.**
"Not accessed in 30 days" is NEVER sufficient for deletion of important knowledge.

## Session snapshot GC (v1.8.0)

Configurable cleanup of `sessions/.snapshots/`:

- `max_snapshot_age_days` (default 30)
- `max_snapshot_count` (default 20)
- `max_snapshot_bytes` (default 0 = unlimited)

The **active recovery point** (most recent snapshot) is NEVER deleted.
Dry-run report is generated before any destructive cleanup.

## Concurrency + atomic writes (v1.8.0)

All Markdown mutations use atomic writes (`irag_atomic.py`):

- `atomic_write_text()`: temp file -> fsync -> `os.replace`
- `ProjectWriteLock`: cross-platform file lock (O_EXCL + fcntl on POSIX)
  with stale-lock detection and timeout

Applied to: `save_working`, `save_checkpoint`, `_append_history`, task state, fingerprint cache.
