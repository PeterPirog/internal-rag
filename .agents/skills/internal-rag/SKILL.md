---
name: internal-rag
description: Mandatory persistent project memory for substantial coding tasks. Use at task start, recovery, milestones, failures, before risky operations, before compaction, and before finishing. v1.0.0 adds CRUD, multi-task stack, MCP server, optional embeddings, doctor, export/import.
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

If `RECOVERY REQUIRED` appears, do not make new edits. Inspect Git state, reconstruct unfinished work, checkpoint it, then run `guard`.

## Before the first code edit

Create a task-start checkpoint:

```bash
python3 .agents/skills/internal-rag/irag.py checkpoint --reason "task-start" --phase "starting implementation" --next "first concrete implementation step"
```

On Windows use `python` instead of `python3`.

## Checkpoint frequently

Checkpoint after each meaningful milestone, important discovery, blocker/failure, or plan change, and before dependency installs, large builds/tests, migrations, broad refactors, compaction, and the final answer.

Example:

```bash
python3 .agents/skills/internal-rag/irag.py checkpoint \
  --reason "milestone" \
  --phase "scheduler migration" \
  --completed "auth middleware migrated; auth tests pass" \
  --in-progress "scheduler callers" \
  --blockers "none" \
  --next "migrate scheduler refresh path; run scheduler tests"
```

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

Retrieval uses BM25 + MMR by default. If `sentence-transformers` is installed and `.irag.yml` enables it, embeddings are used with BM25 fallback.

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