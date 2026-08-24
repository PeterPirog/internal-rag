# Privacy & Git (v1.0.1)

## Default policy

`INTERNAL_RAG/` is local operational memory and may contain local paths, hypotheses, and operational info. Never store secrets in it.

## Why `.git/info/exclude`

v1.0 uses `.git/info/exclude` by default instead of the project's `.gitignore`. This is local to a single clone and is not committed.

`local` mode excludes:
- `INTERNAL_RAG/` (including `.index.sqlite3` SQLite cache),
- the INTERNAL_RAG skill,
- OpenCode tools/commands/plugin for INTERNAL_RAG,
- `.irag.yml`,
- `AGENTS.md` only when the installer created it from scratch.

If the project already had a tracked `AGENTS.md`, its modification will be visible in Git. The uninstaller removes only the marked INTERNAL_RAG section.

## Ignore does not affect tracked files

If a file was already added to Git, a later ignore/exclude does not stop tracking it.

Before a push run:

```text
privacy_check.py
```

Expected: `RESULT: PASS`.

The checker audits:
- presence of the local exclude block,
- tracked INTERNAL_RAG/tool/`.irag.yml` files,
- common credential patterns in `INTERNAL_RAG/`,
- `INTERNAL_RAG/` paths in git commit history.

It never prints the values of found secrets.

## If INTERNAL_RAG was committed

Deleting files does not remove data from Git history. Use a separate history cleanup tool such as `git filter-repo`.

## Should I add anything to the project `.gitignore`?

By default: **no**.

If the whole team consciously wants to ignore memory collectively, add:

```gitignore
/INTERNAL_RAG/
/.irag.yml
```