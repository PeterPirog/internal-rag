---
name: internal-rag
description: Mandatory persistent project memory for substantial coding tasks. Use at task start, recovery, milestones, failures, before risky operations, before compaction, and before finishing. v1.0.1 adds type filtering, type-priority scoring, query expansion, grouped context output, and promote workflow.
---

# Internal RAG

## Start every substantial task

Windows:
```powershell
python .agents\skills\internal-rag\irag.py context --task "<current task>"
```

Linux/macOS:
```bash
python3 .agents/skills/internal-rag/irag.py context --task "<current task>"
```

The context packet groups memories by type:
- **Verified facts** (decisions, knowledge, constraints) — trust these as established context.
- **Lessons & pitfalls** (gotchas, failures) — apply to avoid repeating mistakes.
- **Unverified hypotheses** — treat as tentative ideas, not facts. Verify before acting.

If `RECOVERY REQUIRED` appears, do not make new edits. Inspect Git state, reconstruct unfinished work, checkpoint it, then run `guard`.

## Filtering by type or status

```bash
# Only decisions and knowledge (verified facts)
irag.py search --query "database" --type decision knowledge

# Only active memories (exclude tentative)
irag.py search --query "cache" --status active

# Only hypotheses (what's still unverified)
irag.py search --query "performance" --type hypothesis

# Combine in context
irag.py context --task "fix database pool" --type decision gotcha --status active
```

## Before the first code edit

Create a task-start checkpoint:

```bash
python3 .agents/skills/internal-rag/irag.py checkpoint --reason "task-start" --phase "starting implementation" --next "first concrete implementation step"
```

On Windows use `python` instead of `python3`.

## Checkpoint frequently

Checkpoint after each meaningful milestone, important discovery, blocker/failure, or plan change, and before dependency installs, large builds/tests, migrations, broad refactors, compaction, and the final answer.

## Guard before finishing

```bash
python3 .agents/skills/internal-rag/irag.py guard
```

If guard is stale, checkpoint and run guard again. Do not finish until `GUARD OK`.

## Retrieval (selective, never preload all)

```bash
python3 .agents/skills/internal-rag/irag.py search --query "symbols subsystem error" --limit 8
python3 .agents/skills/internal-rag/irag.py search --query "..." --json   # for tooling
```

Retrieval uses BM25 + MMR by default with **type-priority scoring** (decisions > knowledge > constraints > gotchas > failures > hypotheses). If `sentence-transformers` is installed and `.irag.yml` enables it, embeddings are used with BM25 fallback. The query is automatically expanded with synonyms (e.g. "db" → "database", "auth" → "authentication") for better recall.

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

## Durable memory CRUD

Store only future-relevant knowledge. Never save raw chain-of-thought.

```bash
# Create
python3 .agents/skills/internal-rag/irag.py remember --type decision --title "..." --body "..." --tags "a,b" --scope "module" --evidence "src/x.py:42"

# Read
python3 .agents/skills/internal-rag/irag.py show <path-or-id>
python3 .agents/skills/internal-rag/irag.py timeline --limit 20

# Update
python3 .agents/skills/internal-rag/irag.py update <ref> --status superseded --add-tags "new"
python3 .agents/skills/internal-rag/irag.py update <ref> --append "New evidence: ..."

# Lifecycle
python3 .agents/skills/internal-rag/irag.py supersede <ref> --by <new-ref> --reason "..."
python3 .agents/skills/internal-rag/irag.py forget <ref>      # moves to archive/
python3 .agents/skills/internal-rag/irag.py link --from <ref> --to <ref>

# Overview
python3 .agents/skills/internal-rag/irag.py status
python3 .agents/skills/internal-rag/irag.py diff
```

## Promote workflow (hypothesis → verified knowledge)

When a hypothesis is confirmed:

```bash
# 1. Create the verified memory
irag.py remember --type knowledge --title "Confirmed: X causes Y" --body "Verified by test Z." --status active

# 2. Supersede the hypothesis
irag.py supersede <hypothesis-ref> --by <new-knowledge-ref> --reason "confirmed in test Z"
```

When a hypothesis is disproven:

```bash
irag.py update <hypothesis-ref> --status invalid --append "Disproved by test Z."
```

## Multi-task stack (interrupts)

When interrupted mid-task, push it and resume later:

```bash
python3 .agents/skills/internal-rag/irag.py push --task "interrupted work" --reason "user-priority"
python3 .agents/skills/internal-rag/irag.py tasks
python3 .agents/skills/internal-rag/irag.py resume
```

`resume` restores the pushed WORKING_STATE and reports whether project code still matches.

## Compaction

Before context compaction, archive and trim WORKING_STATE:

```bash
python3 .agents/skills/internal-rag/irag.py compact
```

## Diagnostics & transfer

```bash
python3 .agents/skills/internal-rag/irag.py doctor
python3 .agents/skills/internal-rag/irag.py embeddings-info
python3 .agents/skills/internal-rag/irag.py export                 # -> INTERNAL_RAG/exports/
python3 .agents/skills/internal-rag/irag.py import <file.json> --overwrite
python3 .agents/skills/internal-rag/irag.py config
python3 .agents/skills/internal-rag/irag.py history
```

## Optional Git hooks (auto-checkpoint)

```bash
python3 .agents/skills/internal-rag/irag_hooks.py install
python3 .agents/skills/internal-rag/irag_hooks.py status
python3 .agents/skills/internal-rag/irag_hooks.py uninstall
```

Hooks never block git operations.

## MCP server (for Claude Code / Cursor / etc.)

```bash
python3 .agents/skills/internal-rag/irag.py mcp
```

Speaks a minimal JSON-RPC stdio protocol exposing `context`, `search`, `checkpoint`, `guard`, `remember`, `status`, `tasks`, `resume`.

## Privacy and Git

`INTERNAL_RAG/` is local operational memory and may contain private project context.
Never intentionally save passwords, tokens, API keys, private keys, credentials, or production data.
The installer normally keeps INTERNAL_RAG and its integration files out of the target project's commits using `.git/info/exclude`.
Before publishing a repository, use the package-level `privacy_check.py`.