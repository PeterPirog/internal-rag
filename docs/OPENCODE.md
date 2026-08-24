# OpenCode (v1.0.1)

OpenCode uses:
- `.agents/skills/internal-rag/SKILL.md`,
- `.opencode/tools/`,
- `.opencode/plugins/internal-rag-resilience.ts`,
- `.opencode/commands/`.

## Tools (native)

- `memory-context` — start/resume a task (context packet + recovery).
- `memory-search` — BM25+MMR/embeddings search.
- `memory-checkpoint` — save state.
- `memory-guard` — verify freshness.
- `memory-remember` — store durable memory.
- `memory-status` — memory overview.

All tools support `--json` where relevant.

## Commands (slash)

- `/memory <task>` — start a task.
- `/checkpoint` — save state + guard.
- `/memory-check` — index + status + validate + guard.
- `/memory-guard` — guard only.

## Plugin (resilience)

`internal-rag-resilience.ts`:
- `tool.execute.after` — auto-checkpoint after `edit`/`write`/`apply_patch`.
- `session.error` — checkpoint + suggest inspection.
- `session.idle` — checkpoint.
- `experimental.session.compacting` — `compact` + checkpoint + inject WORKING_STATE into context.

If a native tool fails, the agent can always call `irag.py` via the terminal.