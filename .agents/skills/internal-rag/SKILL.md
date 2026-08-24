---
name: internal-rag
description: Mandatory persistent project memory for substantial coding tasks. Use at task start, recovery, milestones, failures, before risky operations, before compaction, and before finishing.
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

## Retrieval

Do not recursively read all of `INTERNAL_RAG/`.

```bash
python3 .agents/skills/internal-rag/irag.py search --query "symbols subsystem error" --limit 8
```

## Durable memory

Use `remember` only for future-relevant decisions, constraints, root causes, gotchas, failures, and hypotheses. Never save raw chain-of-thought.

## Privacy and Git

`INTERNAL_RAG/` is local operational memory and may contain private project context.
Never intentionally save passwords, tokens, API keys, private keys, credentials, or production data.
The installer normally keeps INTERNAL_RAG and its integration files out of the target project's commits using `.git/info/exclude`.
Before publishing a repository, use the package-level `privacy_check.py`.
