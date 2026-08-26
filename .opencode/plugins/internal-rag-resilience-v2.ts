// OpenCode 2 plugin: MCP Light Memory resilience hooks.
//
// Uses the V2 RUNTIME plugin API (not the stable V1 hooks-object API):
//   import { Plugin } from "@opencode-ai/plugin"
//   export default Plugin.define({ id, setup(ctx) { ... } })
//
//   - runtime hook registration: ctx.tool.hook("execute.after", handler)
//   - session events (documented names only):
//     ctx.session.hook("session.error" | "session.idle" | "session.compacted", handler)
//   - the V1 pre-compaction hook has no documented V2 equivalent, so the
//     documented `session.compacted` event is used for the post-compaction
//     checkpoint + state surfacing.
//
// Known V2 limitation (NOT silently swallowed): GitHub issue anomalyco/opencode#44788
// reports that event delivery does not work on some V2 builds — the session
// hooks below may not fire. The MCP PULL-based workflow (memory-checkpoint /
// memory-guard tools) remains the primary resilience path.
//
// `setup` returns a cleanup that disposes every registration and aborts
// in-flight checkpoint spawns.
//
// Installation:
//   install.py --client opencode2 copies ONLY this file (not the V1 plugin),
//   or place manually in .opencode/plugins/.
import { Plugin } from "@opencode-ai/plugin"
import { readFile } from "node:fs/promises"
import { join } from "node:path"

const py = process.platform === "win32" ? "python" : "python3"

type Registration = { dispose?: () => void } | undefined

export default Plugin.define({
  id: "mcp-light-memory.resilience",

  setup(ctx: any) {
    const worktree: string = ctx?.worktree ?? ctx?.directory ?? process.cwd()
    const script = join(worktree, ".agents", "skills", "internal-rag", "mlm.py")

    const registrations: Registration[] = []
    const controllers = new Set<AbortController>()

    const log = (msg: string) => {
      console.error(`[mcp-light-memory.resilience] ${msg}`)
    }

    // Debounce: at least 60s between auto-checkpoints, count skipped
    let lastAutoCheckpoint = 0
    let skippedCount = 0

    const runScript = (args: string[], label: string) => {
      const controller = new AbortController()
      controllers.add(controller)
      let p
      try {
        p = Bun.spawn([py, script, ...args], {
          cwd: worktree,
          stdout: "ignore",
          stderr: "pipe",
          stdin: "ignore",
        })
      } catch (e: any) {
        log(`${label} spawn failed: ${e?.message ?? e}`)
        controllers.delete(controller)
        return Promise.resolve()
      }
      return (async () => {
        try {
          const err = await (p.stderr?.text() ?? Promise.resolve(""))
          const code = await p.exited
          if (code !== 0) log(`${label} failed (exit ${code}): ${err.trim().slice(0, 200)}`)
        } catch (e: any) {
          log(`${label} failed: ${e?.message ?? e}`)
        } finally {
          controllers.delete(controller)
        }
      })()
    }

    const cp = (reason: string, phase?: string) => {
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

    const afterCompaction = async () => {
      await cp("opencode2-after-compaction", "Context compaction; resume from persistent state.")
      let state = "(unavailable)"
      try {
        state = await readFile(join(worktree, "INTERNAL_RAG", "WORKING_STATE.md"), "utf8")
      } catch (e: any) {
        log(`WORKING_STATE.md unavailable: ${e?.message ?? e}`)
      }
      log(`post-compaction WORKING_STATE (first 2000 chars):\n${state.slice(0, 2000)}`)
    }

    // --- tool hook: primary resilience path ---
    let toolReg: Registration
    try {
      toolReg = ctx?.tool?.hook?.("execute.after", async (input: any) => {
        try {
          if (["edit", "write", "apply_patch"].includes(input?.tool)) {
            await debouncedCp(`opencode2-auto-after-${input.tool}`)
          }
        } catch (e: any) {
          log(`execute.after handler failed: ${e?.message ?? e}`)
        }
      })
    } catch (e: any) {
      log(`failed to register tool hook execute.after: ${e?.message ?? e}`)
    }
    if (toolReg !== undefined) registrations.push(toolReg)

    // --- session events: documented V2 event names only (best-effort) ---
    const sessionHandlers: Array<[string, () => Promise<void>]> = [
      ["session.error", () => cp("opencode2-session-error",
        "Session error; inspect prior output and Git state before continuing.")],
      ["session.idle", () => debouncedCp("opencode2-session-idle")],
      ["session.compacted", () => afterCompaction()],
    ]

    for (const [name, handler] of sessionHandlers) {
      let reg: Registration
      try {
        reg = ctx?.session?.hook?.(name, async (_input: any) => {
          try {
            await handler()
          } catch (e: any) {
            log(`${name} handler failed: ${e?.message ?? e}`)
          }
        })
      } catch (e: any) {
        log(`failed to register session hook ${name}: ${e?.message ?? e}`)
        continue
      }
      if (reg !== undefined) registrations.push(reg)
    }

    log(`ready: ${registrations.length} registration(s); ` +
        `fallback = MCP pull-based workflow (memory-checkpoint/memory-guard)`)

    // --- cleanup: abort in-flight spawns, dispose registrations ---
    return () => {
      for (const c of controllers) {
        try {
          c.abort()
        } catch (e: any) {
          log(`abort failed: ${e?.message ?? e}`)
        }
      }
      controllers.clear()
      for (const r of registrations) {
        try {
          ;(r as any)?.dispose?.()
        } catch (e: any) {
          log(`dispose failed: ${e?.message ?? e}`)
        }
      }
      registrations.length = 0
    }
  },
})
