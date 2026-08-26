// OpenCode 2 (beta) plugin: MCP Light Memory resilience hooks.
//
// WARNING: OpenCode 2 is still in beta. Its plugin API may change without
// notice. This file is a best-effort compatibility layer using the
// documented V2 plugin patterns. If the V2 plugin API breaks, MCP Light
// Memory will still work via MCP tools (context/search/remember/guard) —
// the plugin only adds auto-checkpoint/compact convenience hooks.
//
// Key differences from V1:
//   - V2 uses ctx.tool.hook("execute.after", ...) instead of "tool.execute.after"
//   - V2 uses ctx.event(...) instead of event({...})
//   - V2 session compaction hook name may differ
//
// Installation for OpenCode 2:
//   Place in .opencode/plugins/ (auto-loaded by V2 as well).
//   The V1 plugin (internal-rag-resilience.ts) can coexist — V2 will ignore
//   V1-style return shapes and V1 will ignore V2-style hooks.
//
// Limitations:
//   - If V2 does not support the exact hook names used here, the hooks will
//     be silently ignored. MCP Light Memory core functionality (MCP tools)
//     is unaffected.
//   - No auto-compaction in V2 if the session.compacting hook is unavailable.

const py = process.platform === "win32" ? "python" : "python3"

export default async (ctx: any) => {
  // ctx is the V2 plugin context. We use optional chaining extensively
  // because the V2 API is still beta and may not expose all methods.

  const worktree = ctx?.worktree || ctx?.cwd || process.cwd()
  const script = [worktree, ".agents", "skills", "internal-rag", "mlm.py"].join("/")

  let lastAutoCheckpoint = 0
  let skippedCount = 0

  const cp = async (reason: string, phase?: string) => {
    try {
      const c = [py, script, "checkpoint", "--reason", reason]
      if (phase) c.push("--phase", phase)
      const p = Bun.spawn(c, { cwd: worktree, stdout: "ignore", stderr: "ignore" })
      await p.exited
    } catch {}
  }

  const debouncedCp = async (reason: string, phase?: string) => {
    const now = Date.now()
    if (now - lastAutoCheckpoint < 60_000) {
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

  const compact = async () => {
    try {
      const p = Bun.spawn([py, script, "compact"], { cwd: worktree, stdout: "ignore", stderr: "ignore" })
      await p.exited
    } catch {}
  }

  // V2 hook registration (best-effort)
  if (ctx?.tool?.hook) {
    try {
      ctx.tool.hook("execute.after", async (input: any, _output: any) => {
        if (["edit", "write", "apply_patch"].includes(input?.tool)) {
          await debouncedCp(`opencode2-auto-after-${input.tool}`)
        }
      })
    } catch {}
  }

  if (ctx?.event) {
    try {
      ctx.event(async (event: any) => {
        if (event?.type === "session.error") {
          await cp("opencode2-session-error")
        } else if (event?.type === "session.idle") {
          await cp("opencode2-session-idle")
        }
      })
    } catch {}
  }

  // V2 compaction hook (best-effort — name may differ in V2)
  if (ctx?.session?.compacting) {
    try {
      ctx.session.compacting(async (_input: any, output: any) => {
        await compact()
        await cp("opencode2-before-compaction")
        if (output?.context) {
          try {
            const state = await Bun.file([worktree, "INTERNAL_RAG", "WORKING_STATE.md"].join("/")).text()
            output.context.push(`\n## Persistent project memory\n${state}\n`)
          } catch {}
        }
      })
    } catch {}
  }

  return {}
}