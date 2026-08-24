# Daily usage (v1.0.1)

## Start a task

```text
irag.py context --task "task description"
```

For tooling: `irag.py context --task "..." --json`.

## Before the first change

```text
irag.py checkpoint --reason "task-start"
```

## After a milestone

```text
irag.py checkpoint --reason "milestone" --phase "..." --completed "..." --next "..."
```

## Search memory

```text
irag.py search --query "symbol subsystem problem" --limit 8
irag.py search --query "..." --json
irag.py search --query "..." --embeddings off
```

BM25+MMR by default; embeddings when available and enabled in `.irag.yml` (or `--embeddings on`).

## Store durable knowledge

```text
irag.py remember --type decision --title "..." --scope "..." --tags "..." --evidence "..." --body "..." --consequence "..." --links "decisions/other.md"
```

Types: `decision`, `knowledge`, `constraint`, `gotcha`, `failure`, `hypothesis`, `session`.

## Read / update memory

```text
irag.py show <path-or-id>
irag.py show <ref> --section Knowledge
irag.py timeline --limit 20
irag.py update <ref> --status superseded --add-tags "new"
irag.py update <ref> --append "New evidence: ..."
irag.py supersede <ref> --by <new-ref> --reason "..."
irag.py forget <ref>
irag.py link --from <ref> --to <ref>
irag.py status
irag.py diff
irag.py history
```

## Task stack (interrupts)

```text
irag.py push --task "interrupted work" --reason "user-priority"
irag.py tasks
irag.py resume
irag.py forget-task <id>
irag.py forget-task
```

## Compaction (before context compaction)

```text
irag.py compact
```

## Diagnostics

```text
irag.py doctor
irag.py embeddings-info
irag.py config
irag.py config --init
irag.py validate
irag.py index
```

## Transfer memory

```text
irag.py export
irag.py import <file.json> --overwrite
```

## Finish

```text
irag.py guard
```

Finish only after `GUARD OK`.

## Never store

Passwords, tokens, API keys, private keys, production data, full logs, full chain-of-thought, or the entire conversation history.