# INTERNAL_RAG

![version](https://img.shields.io/badge/version-1.0.1-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![python](https://img.shields.io/badge/python-3.8%2B-blue)

Local, persistent project memory for terminal coding agents (Warp, OpenCode, Claude Code, Cursor).

**Version:** 1.1.0  
**Verified:** 2026-08-24  
**Integrations:** Warp, OpenCode, MCP (Claude Code / Cursor)  
**Requirements:** Python 3.8+, Git  
**Optional:** `sentence-transformers`, `numpy` (better semantic retrieval)  
**Offline:** Fully functional without internet (BM25 core, optional pre-packaged embeddings)

INTERNAL_RAG stores the minimum state needed to resume complex work without keeping the full session history in the model's context window. It works as a checkpoint + RAG for the agent.

## What's new in 1.0.2

- **Token budget enforcement**: `context` cuts memories to fit `context_budget` (sorted by score).
- **Stale memory detection**: `validate` warns when evidence paths no longer exist.
- **Duplicate detection**: `remember` blocks duplicates (use `--force` to override).
- **Privacy scan at write-time**: `remember` refuses secrets (use `--allow-secret` to bypass).
- **Auto-checkpoint timer**: `guard`/`context` warn if checkpoint is too old (`max_age_minutes`).
- **Recent commits in context**: `context` shows last 5 git commits for recovery.
- **Offline / air-gapped**: `pack.py` creates self-contained ZIP with wheels + model.

- Full English documentation.
- `search --json` now returns `matched_tokens`.
- `remember --links` stored in frontmatter.
- MCP server handles `notifications/initialized` and `shutdown`.
- `compact` preserves sections (trims long lists, not the structure).
- `privacy_check.py` now audits `.irag.yml`.
- `requirements-optional.txt` for embeddings.
- `--quiet` / `--verbose` global flags.
- `history` command (checkpoint history).
- `forget-task <id>` (drop a specific task, not just clear-all).
- `resume` updates WORKING_STATE sections.
- `config --init` generates a `.irag.yml` template.
- `--embeddings on|off|auto` CLI override.
- `show --section <name>` extracts a single section.
- Schema versioning in `.checkpoint.json` / `.tasks.json`.
- `.gitignore` covers `.tasks.json`, `.fpcache.json`, `exports/`.
- New docs: `docs/CLI.md`, `docs/GIT-HOOKS.md`.
- README badges.
- Extended `self_test.py` (CRUD, MCP, hooks).

## What's new in 1.0.0

- **BM25 + MMR retrieval** with optional embeddings (zero-dep fallback).
- **Full memory CRUD**: `show`, `update`, `supersede`, `forget`, `link`, `status`, `diff`, `timeline`.
- **Task stack**: `push` / `tasks` / `resume` / `forget-task` for interrupts.
- **Compaction**: `compact` before context compaction.
- **MCP server**: `irag.py mcp` (JSON-RPC stdio) for Claude Code / Cursor.
- **Git hooks** (optional): auto-checkpoint after commit, pre-push warning.
- **Diagnostics**: `doctor`, `embeddings-info`, `config`.
- **Memory transfer**: `export` / `import` (JSON).
- **Token budget**: token estimation in `context`.
- **`--json`** for all structured commands.

## Quick start

### Windows

```powershell
python .\install.py "D:\path\to\project"
```

Then restart Warp/OpenCode and in the project:

```powershell
python .agents\skills\internal-rag\irag.py context --task "current task"
```

### Linux/macOS

```bash
python3 install.py "/path/to/project"
```

Then:

```bash
python3 .agents/skills/internal-rag/irag.py context --task "current task"
```

## Workflow

```text
context
  ↓
recovery, if required
  ↓
checkpoint before first change
  ↓
implementation
  ↓
checkpoint after each milestone
  ↓
guard before finishing
```

Core commands:

```text
irag.py context --task "..."
irag.py checkpoint --reason "..."
irag.py search --query "..." --limit 8
irag.py remember --type decision --title "..." --body "..."
irag.py show <ref>
irag.py update <ref> --status superseded
irag.py status
irag.py guard
irag.py validate
irag.py doctor
```

## Durable memory (CRUD)

```text
remember --type decision --title "..." --body "..." --tags "a,b" --evidence "src/x.py:42" --links "decisions/other.md"
show <path-or-id>
show <ref> --section Knowledge
update <ref> --add-tags "new" --append "New evidence: ..."
supersede <ref> --by <new> --reason "..."
forget <ref>              # archives, does not delete
link --from <ref> --to <ref>
timeline --limit 20
status
history
```

Types: `decision`, `knowledge`, `constraint`, `gotcha`, `failure`, `hypothesis`, `session`.

## Task stack (interrupts)

```text
irag.py push --task "interrupted work" --reason "user-priority"
irag.py tasks
irag.py resume
irag.py forget-task <id>   # drop a specific task
irag.py forget-task         # clear the whole stack
```

## MCP server (Claude Code / Cursor)

```bash
python3 .agents/skills/internal-rag/irag.py mcp
```

Minimal JSON-RPC stdio: `context`, `search`, `checkpoint`, `guard`, `remember`, `status`, `tasks`, `resume`.

## Git hooks (optional, auto-checkpoint)

```bash
python3 .agents/skills/internal-rag/irag_hooks.py install
python3 .agents/skills/internal-rag/irag_hooks.py status
python3 .agents/skills/internal-rag/irag_hooks.py uninstall
```

Hooks never block git operations.

## Configuration (`.irag.yml`, optional)

```yaml
retrieval:
  limit: 10
  mmr_lambda: 0.4
  min_score: 0.3
  embeddings: auto        # auto | on | off
  embeddings_model: all-MiniLM-L6-v2
tokens:
  context_budget: 5000
checkpoints:
  auto_archive_sessions: true
  max_task_stack: 24
```

`irag.py config` shows the effective configuration. `irag.py config --init` writes a template.

## Diagnostics & transfer

```text
irag.py doctor
irag.py embeddings-info
irag.py export                  # -> INTERNAL_RAG/exports/
irag.py import <file.json> --overwrite
irag.py config
irag.py history
```

## Optional embeddings (better retrieval)

```bash
pip install -r requirements-optional.txt
```

When the package is available and `.irag.yml` has `embeddings: auto` (default), retrieval uses embeddings with fallback to BM25. Override at runtime with `--embeddings on|off|auto`.

## Offline / air-gapped

INTERNAL_RAG works fully offline (BM25 core, zero dependencies). For embeddings on air-gapped machines:

```bash
# On a machine with internet:
python pack.py --with-embeddings --model all-MiniLM-L6-v2
# -> internal-rag-offline-1.0.2.zip

# On the air-gapped machine:
unzip internal-rag-offline-*.zip -d internal-rag-offline
cd internal-rag-offline
pip install --no-index --find-links wheels/ -r requirements-optional.txt
python install.py "/path/to/project"
```

See `docs/OFFLINE.md` for details.

## Privacy & Git

The default install mode is **local-only**. The installer uses `.git/info/exclude`, not the project's `.gitignore`, so local memory and integration files are not accidentally committed.

Before publishing a project:

```powershell
python .\privacy_check.py "D:\path\to\project"
```

Expected result:

```text
RESULT: PASS
```

## Full removal from a project

```powershell
python .\uninstall.py "D:\path\to\project"
```

The uninstaller creates a backup outside the repository, then removes INTERNAL_RAG and its integrations. To keep the memory, use `--keep-memory`.

## Documentation

- [Installation](docs/INSTALLATION.md)
- [Daily usage](docs/DAILY-USAGE.md)
- [CLI reference](docs/CLI.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Memory lifecycle](docs/MEMORY-LIFECYCLE.md)
- [Recovery](docs/RECOVERY.md)
- [Warp](docs/WARP.md)
- [OpenCode](docs/OPENCODE.md)
- [MCP](docs/MCP.md)
- [Configuration](docs/CONFIG.md)
- [Embeddings](docs/EMBEDDINGS.md)
- [Offline / air-gapped](docs/OFFLINE.md)
- [Git hooks](docs/GIT-HOOKS.md)
- [Privacy & Git](docs/PRIVACY-AND-GIT.md)
- [Uninstall](docs/UNINSTALL.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [File map](docs/FILE-MAP.md)
- [Compatibility](docs/COMPATIBILITY.md)
- [GitHub publishing](docs/GITHUB-PUBLISHING.md)

## Structure in a target project

```text
project/
├── AGENTS.md
├── .irag.yml                    # optional config
├── INTERNAL_RAG/
│   ├── WORKING_STATE.md
│   ├── INDEX.md
│   ├── .checkpoint.json
│   ├── .tasks.json
│   ├── .fpcache.json
│   ├── exports/
│   ├── decisions/
│   ├── knowledge/
│   ├── gotchas/
│   ├── failures/
│   ├── hypotheses/
│   ├── sessions/
│   │   └── .snapshots/
│   └── archive/
├── .agents/skills/internal-rag/
│   ├── SKILL.md
│   ├── irag.py
│   ├── irag_embeddings.py       # optional plugin
│   └── irag_hooks.py            # optional git hooks
└── .opencode/
    ├── tools/
    ├── commands/
    └── plugins/
```

## Source of truth

1. current user instructions,
2. current code/tests/configuration,
3. specifications/ADRs,
4. verified memory,
5. session notes,
6. hypotheses.

Memory can be stale. Code takes precedence.

## License

MIT.