import type { Plugin } from "@opencode-ai/plugin"
import { readFile } from "node:fs/promises"
import { join } from "node:path"
const py = process.platform === "win32" ? "python" : "python3"

export const InternalRagResilience: Plugin = async ({ worktree }) => {
  const script = join(worktree, ".agents", "skills", "internal-rag", "mlm.py")

  // H3: debounce — at least 60s between auto-checkpoints, count skipped
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
    const minInterval = 60_000 // 60 seconds
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
      const p = Bun.spawn([py, script, "compact"], { cwd: worktree, stdout: "ignore", stderr: "ignore" })
      await p.exited
    } catch {}
  }

  return {
    "tool.execute.after": async (input, _output) => {
      if (["edit", "write", "apply_patch"].includes(input.tool)) {
        await debouncedCp(`opencode-auto-after-${input.tool}`)
      }
    },
    event: async ({ event }) => {
      if (event.type === "session.error") {
        await cp("opencode-session-error", "Session error; inspect prior output and Git state before continuing.")
      } else if (event.type === "session.idle") {
        await cp("opencode-session-idle")
      }
    },
    "experimental.session.compacting": async (_input, output) => {
      await compact()
      await cp("opencode-before-compaction", "Context compaction; resume from persistent state.")
      let state = "(unavailable)"
      try {
        state = await readFile(join(worktree, "INTERNAL_RAG", "WORKING_STATE.md"), "utf8")
      } catch {}
      output.context.push(`\n## Persistent project memory\n${state}\nContinue using checkpoint/guard discipline.\n`)
    }
  }
}