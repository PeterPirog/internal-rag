import { tool } from "@opencode-ai/plugin"
const py = process.platform === "win32" ? "python" : "python3"
const script = (worktree: string) => `${worktree}/.agents/skills/internal-rag/mlm.py`
export default tool({
  description: "Start/resume a task using INTERNAL_RAG and detect missed checkpoints. Returns a context packet with WORKING_STATE, candidate memories, token estimates, and recovery guidance.",
  args: {
    task: tool.schema.string(),
    limit: tool.schema.number().optional(),
    json: tool.schema.boolean().optional(),
  },
  async execute(args, context) {
    const cmd = [py, script(context.worktree), "context", "--task", args.task]
    if (args.limit) cmd.push("--limit", String(args.limit))
    if (args.json) cmd.push("--json")
    const p = Bun.spawn(cmd, { cwd: context.worktree, stdout: "pipe", stderr: "pipe" })
    const o = await new Response(p.stdout).text()
    const e = await new Response(p.stderr).text()
    const c = await p.exited
    if (c !== 0) throw new Error(e || `exit ${c}`)
    return o.trim()
  }
})