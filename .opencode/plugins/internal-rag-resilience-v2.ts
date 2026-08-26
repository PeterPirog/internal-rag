// OpenCode 2 plugin: MCP Light Memory resilience hooks.
//
// Uses the V2 RUNTIME plugin API documented at
// https://opencode.ai/v2/docs/build/plugins (NOT the V1 hooks-object API):
//   import { Plugin } from "@opencode-ai/plugin"
//   export default Plugin.define({ id, async setup(ctx) { ... } })
//
//   - runtime hook registration (awaited): await ctx.tool.hook("execute.after", ...)
//     ctx.tool.hook(...) and ctx.session.hook(...) return Promise<Registration>.
//   - public server events (session.error/session.idle/session.compacted are NOT
//     SessionHooks — they are public events) are received via the documented
//     ctx.event.subscribe({ signal }) AsyncIterable.
//   - Documented V2 SessionHooks: context, model.request, http.request,
//     http.response. This plugin does not currently register any of them.
//
// Known V2 limitation (NOT silently swallowed): GitHub issue
// anomalyco/opencode#44788 reports that event delivery does not work on some
// V2 builds — the event stream below may not yield any events. The MCP
// PULL-based workflow (memory-checkpoint / memory-guard tools) remains the
// primary resilience path. The hook on tool.execute.after is the primary
// auto-checkpoint trigger and does not depend on event delivery.
//
// `setup` returns a cleanup that disposes every awaited Registration and
// aborts the event-stream AbortController.
//
// Installation:
//   install.py --client opencode2 copies ONLY this file (not the V1 plugin),
//   or place manually in .opencode/plugins/.
import { Plugin, type Registration } from "@opencode-ai/plugin"
import { readFile } from "node:fs/promises"
import { join } from "node:path"

const py = process.platform === "win32" ? "python" : "python3"

// Public event types we react to. These are NOT SessionHook names; they are
// server-emitted public events received through ctx.event.subscribe.
type EventKey = "session.error" | "session.idle" | "session.compacted"

const EVENT_HANDLERS: Array<{ key: EventKey; reason: string; phase?: string }> = [
  {
    key: "session.error",
    reason: "opencode2-session-error",
    phase: "Session error; inspect prior output and Git state before continuing.",
  },
  {
    key: "session.idle",
    reason: "opencode2-session-idle",
  },
  {
    key: "session.compacted",
    reason: "opencode2-after-compaction",
    phase: "Context compaction; resume from persistent state.",
  },
]

function eventKeyOf(event: { type?: string } | string | null | undefined): EventKey | undefined {
  if (event == null) return undefined
  const t = typeof event === "string" ? event : event.type
  if (typeof t !== "string") return undefined
  return EVENT_HANDLERS.some((h) => h.key === t) ? (t as EventKey) : undefined
}

export default Plugin.define({
  id: "mcp-light-memory.resilience",

  async setup(ctx: any) {
    const worktree: string = ctx?.worktree ?? ctx?.directory ?? process.cwd()
    const script = join(worktree, ".agents", "skills", "internal-rag", "mlm.py")

    const registrations: Registration[] = []
    const eventController = new AbortController()

    const log = (msg: string) => {
      console.error(`[mcp-light-memory.resilience] ${msg}`)
    }

    // Debounce: at least 60s between auto-checkpoints, count skipped edits.
    let lastAutoCheckpoint = 0
    let skippedCount = 0

    const runScript = async (args: string[], label: string) => {
      let p: any
      try {
        p = Bun.spawn([py, script, ...args], {
          cwd: worktree,
          stdout: "ignore",
          stderr: "pipe",
          stdin: "ignore",
        })
      } catch (e: any) {
        log(`${label} spawn failed: ${e?.message ?? e}`)
        return
      }
      try {
        const err = await (p.stderr?.text() ?? Promise.resolve(""))
        const code = await p.exited
        if (code !== 0) log(`${label} failed (exit ${code}): ${err.trim().slice(0, 200)}`)
      } catch (e: any) {
        log(`${label} failed: ${e?.message ?? e}`)
      }
    }

    const cp = async (reason: string, phase?: string) => {
      const args = ["checkpoint", "--reason", reason]
      if (phase) args.push("--phase", phase)
      return runScript(args, "checkpoint")
    }

    const debouncedCp = async (reason: string, phase?: string) => {
      const now = Date.now()
      const minInterval = 60_000
      if (now - lastAutoCheckpoint < minInterval) {
        skippedCount++
        return
      }
      const effectiveReason = skippedCount > 0
        ? `${reason} (debounced: ${skippedCount} edits skipped)`
        : reason
      lastAutoCheckpoint = now
      skippedCount = 0
      await cp(effectiveReason, phase)
    }

    const surfaceWorkingState = async () => {
      let state = "(unavailable)"
      try {
        state = await readFile(join(worktree, "INTERNAL_RAG", "WORKING_STATE.md"), "utf8")
      } catch (e: any) {
        log(`WORKING_STATE.md unavailable: ${e?.message ?? e}`)
      }
      log(`post-compaction WORKING_STATE (first 2000 chars):\n${state.slice(0, 2000)}`)
    }

    const handleEvent = async (key: EventKey) => {
      const handler = EVENT_HANDLERS.find((h) => h.key === key)
      if (!handler) return
      if (key === "session.compacted") {
        await cp(handler.reason, handler.phase)
        await surfaceWorkingState()
      } else {
        await cp(handler.reason, handler.phase)
      }
    }

    // --- tool hook: primary resilience path (awaited) ---
    if (ctx?.tool?.hook) {
      try {
        const toolReg = await ctx.tool.hook("execute.after", async (event: any) => {
          const toolName = event?.tool
          if (toolName !== "edit" && toolName !== "write" && toolName !== "apply_patch") return
          try {
            await debouncedCp(`opencode2-auto-after-${toolName}`)
          } catch (e: any) {
            log(`execute.after handler failed: ${e?.message ?? e}`)
          }
        })
        if (toolReg !== undefined && toolReg !== null) {
          registrations.push(toolReg as Registration)
        }
      } catch (e: any) {
        log(`failed to register tool hook execute.after: ${e?.message ?? e}`)
      }
    }

    // --- public event stream (ctx.event.subscribe, AsyncIterable) ---
    // session.error/session.idle/session.compacted are public server events,
    // NOT SessionHook names (V2 SessionHooks: context, model.request,
    // http.request, http.response). Receive them through the documented
    // ctx.event.subscribe({ signal }) AsyncIterable.
    if (ctx?.event?.subscribe) {
      const sub: AsyncIterable<{ type?: string }> = ctx.event.subscribe({
        signal: eventController.signal,
      })
      void (async () => {
        try {
          for await (const event of sub) {
            if (eventController.signal.aborted) break
            const key = eventKeyOf(event)
            if (key !== undefined) {
              try {
                await handleEvent(key)
              } catch (e: any) {
                log(`${key} handler failed: ${e?.message ?? e}`)
              }
            }
          }
        } catch (e: any) {
          if (eventController.signal.aborted) return
          log(`event stream failed: ${e?.message ?? e}`)
        }
      })()
    } else {
      log("ctx.event.subscribe unavailable; using MCP pull-based workflow only")
    }

    log(`ready: ${registrations.length} registration(s); ` +
        `fallback = MCP pull-based workflow (memory-checkpoint/memory-guard)`)

    // --- cleanup: abort the event stream, dispose awaited registrations ---
    return () => {
      try {
        eventController.abort()
      } catch (e: any) {
        log(`event abort failed: ${e?.message ?? e}`)
      }
      for (const r of registrations) {
        try {
          const result = r?.dispose?.()
          if (result != null && typeof (result as any).then === "function") {
            void (result as Promise<void>).catch((e: any) =>
              log(`dispose failed: ${e?.message ?? e}`))
          }
        } catch (e: any) {
          log(`dispose failed: ${e?.message ?? e}`)
        }
      }
      registrations.length = 0
    }
  },
})