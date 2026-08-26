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
- `--client opencode2` → `internal-rag-resilience-v2.ts` (V2)

### V1 (stable) — hooks-object API

`internal-rag-resilience.ts` uses the documented hooks-object API
(`return { "tool.execute.after", event, "experimental.session.compacting" }`):

- `tool.execute.after` — auto-checkpoint after `edit`/`write`/`apply_patch` (debounced 60s).
- `session.error` — checkpoint + suggest inspection.
- `session.idle` — checkpoint.
- `experimental.session.compacting` — `compact` + checkpoint + inject WORKING_STATE into context.

### V2 — runtime API

`internal-rag-resilience-v2.ts` uses the V2 runtime plugin API
(`import { Plugin } from "@opencode-ai/plugin"`; `export default Plugin.define({ id, async setup(ctx) { ... } })`):

- stable id `mcp-light-memory.resilience`;
- `async setup(ctx)` **awaits** `ctx.tool.hook("execute.after", ...)` (the
  registration returns `Promise<Registration>`) — auto-checkpoint after
  `edit`/`write`/`apply_patch` (debounced 60s);
- public server events (`session.error`, `session.idle`, `session.compacted`)
  are received through the documented `ctx.event.subscribe({ signal })`
  AsyncIterable — they are public events, NOT `SessionHook` names. The
  documented V2 `SessionHooks` are `context`, `model.request`,
  `http.request`, `http.response`; this plugin does not register any of them;
- `setup` returns a cleanup that **disposes every awaited Registration** and
  **aborts the event-stream `AbortController`**. There is no fake subprocess
  cancellation — Bun subprocesses are awaited to completion (a checkpoint is
  a short-lived `mlm.py` call).

### Common (both)

- All hook failures are logged to stderr (visible in OpenCode logs);
  no empty `catch {}` blocks — nothing is silently swallowed.
- Known V2 limitation: GitHub issue anomalyco/opencode#44788 reports that
  event delivery does not work on some V2 builds — on affected builds the
  event stream may not yield any events. The MCP PULL-based workflow
  (`memory-checkpoint` / `memory-guard` tools) remains the primary
  resilience path. The `tool.execute.after` hook is the primary
  auto-checkpoint trigger and does not depend on event delivery.
- If a native tool fails, the agent can always call `irag.py` via the terminal.