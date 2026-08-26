# OpenCode (v1.7.0)

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

The installer copies exactly ONE plugin, matched to the client (installing
both would double-fire identical hooks):

- `--client opencode` → `internal-rag-resilience.ts` (V1)
- `--client opencode2` → `internal-rag-resilience-v2.ts` (V2 beta)

Both use the documented hooks-object API (`return { "tool.execute.after", event, "experimental.session.compacting" }`):
- `tool.execute.after` — auto-checkpoint after `edit`/`write`/`apply_patch` (debounced 60s).
- `session.error` — checkpoint + suggest inspection.
- `session.idle` — checkpoint.
- `experimental.session.compacting` — `compact` + checkpoint + inject WORKING_STATE into context.

Hook failures are logged to stderr (visible in OpenCode logs); nothing is
silently swallowed.

Known OpenCode 2 beta limitation: GitHub issue anomalyco/opencode#44788
(beta 18050) reports that `event` delivery does not work — on affected
builds the `session.error`/`session.idle`/compacting hooks may not fire.
MCP tools are unaffected.

If a native tool fails, the agent can always call `irag.py` via the terminal.