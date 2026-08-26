// OpenCode 1 (stable) plugin: MCP Light Memory resilience hooks.
//
// Uses the documented hooks-object plugin API (verified against
// https://opencode.ai/docs/plugins/ 2026-08-26):
//   export const Plugin = async (ctx) => { return { "tool.execute.after", event, "experimental.session.compacting" } }
//
// For OpenCode 2 (beta), install.py copies internal-rag-resilience-v2.ts
// instead — do NOT install both (identical hook names would double-fire).
//
// Installation:
//   - OpenCode 1: install.py --client opencode (or place in .opencode/plugins/)
//   - OpenCode 2: install.py --client opencode2
import type { Plugin } from "@opencode-ai/plugin"
import { readFile } from "node:fs/promises"
import { join } from "node:path"

const py = process.platform === "win32" ? "python" : "python3"

export const McpLightMemoryResilience: Plugin = async ({ worktree }) => {
  const script = join(worktree, ".agents", "skills", "internal-rag", "mlm.py")

  // Debounce: at least 60s between auto-checkpoints, count skipped
  let lastAutoCheckpoint = 0
  let skippedCount = 0

  const log = (msg: string) => {
    console.error(`[internal-rag-resilience] ${msg}`)
  }

  const cp = async (reason: string, phase?: string) => {
    const args = [py, script, "checkpoint", "--reason", reason]
    if (phase) args.push("--phase", phase)
    try {
      const p = Bun.spawn(args, { cwd: worktree, stdout: "ignore", stderr: "pipe" })
      const err = await p.stderr?.text().catch(() => "")
      const code = await p.exited
      if (code !== 0) log(`checkpoint failed (exit ${code}): ${err.trim().slice(0, 200)}`)
    } catch (e: any) {
      log(`checkpoint spawn failed: ${e?.message ?? e}`)
    }
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

  const compact = async () => {
    try {
      const p = Bun.spawn([py, script, "compact"], { cwd: worktree, stdout: "ignore", stderr: "pipe" })
      const err = await p.stderr?.text().catch(() => "")
      const code = await p.exited
      if (code !== 0) log(`compact failed (exit ${code}): ${err.trim().slice(0, 200)}`)
    } catch (e: any) {
      log(`compact spawn failed: ${e?.message ?? e}`)
    }
  }

  return {
    "tool.execute.after": async (input: any) => {
      try {
        if (["edit", "write", "apply_patch"].includes(input?.tool)) {
          await debouncedCp(`opencode-auto-after-${input.tool}`)
        }
      } catch (e: any) {
        log(`tool.execute.after hook failed: ${e?.message ?? e}`)
      }
    },
    event: async ({ event }: any) => {
      try {
        if (event?.type === "session.error") {
          await cp("opencode-session-error", "Session error; inspect prior output and Git state before continuing.")
        } else if (event?.type === "session.idle") {
          await cp("opencode-session-idle")
        }
      } catch (e: any) {
        log(`event hook failed: ${e?.message ?? e}`)
      }
    },
    "experimental.session.compacting": async (_input: any, output: any) => {
      try {
        await compact()
        await cp("opencode-before-compaction", "Context compaction; resume from persistent state.")
        let state = "(unavailable)"
        try {
          state = await readFile(join(worktree, "INTERNAL_RAG", "WORKING_STATE.md"), "utf8")
        } catch (e: any) {
          log(`WORKING_STATE.md unavailable: ${e?.message ?? e}`)
        }
        output?.context?.push(`\n## Persistent project memory\n${state}\nContinue using checkpoint/guard discipline.\n`)
      } catch (e: any) {
        log(`session.compacting hook failed: ${e?.message ?? e}`)
      }
    },
  }
}

export default McpLightMemoryResilience
