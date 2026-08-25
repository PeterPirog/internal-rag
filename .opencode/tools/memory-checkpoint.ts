import { tool } from "@opencode-ai/plugin"
const py = process.platform === "win32" ? "python" : "python3"
const script = (worktree: string) => `${worktree}/.agents/skills/internal-rag/mlm.py`
export default tool({
  description: "Persist current operational state. Use before edits, after milestones/failures, before risky operations/compaction/final response.",
  args: {
    reason: tool.schema.string(),
    phase: tool.schema.string().optional(),
    completed: tool.schema.string().optional(),
    in_progress: tool.schema.string().optional(),
    blockers: tool.schema.string().optional(),
    next: tool.schema.string().optional(),
    task: tool.schema.string().optional(),
    objective: tool.schema.string().optional(),
    json: tool.schema.boolean().optional(),
  },
  async execute(args, context) {
    const cmd = [py, script(context.worktree), "checkpoint", "--reason", args.reason]
    if (args.phase) cmd.push("--phase", args.phase)
    if (args.completed) cmd.push("--completed", args.completed)
    if (args.in_progress) cmd.push("--in-progress", args.in_progress)
    if (args.blockers) cmd.push("--blockers", args.blockers)
    if (args.next) cmd.push("--next", args.next)
    if (args.task) cmd.push("--task", args.task)
    if (args.objective) cmd.push("--objective", args.objective)
    if (args.json) cmd.push("--json")
    const p = Bun.spawn(cmd, { cwd: context.worktree, stdout: "pipe", stderr: "pipe" })
    const o = await new Response(p.stdout).text()
    const e = await new Response(p.stderr).text()
    const c = await p.exited
    if (c !== 0) throw new Error(e || `exit ${c}`)
    return o.trim()
  }
})