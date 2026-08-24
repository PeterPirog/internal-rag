import { tool } from "@opencode-ai/plugin"
const py = process.platform === "win32" ? "python" : "python3"
const script = (worktree: string) => `${worktree}/.agents/skills/internal-rag/irag.py`
export default tool({
  description: "INTERNAL_RAG status overview: memory counts by type/status, checkpoint freshness, branch/HEAD.",
  args: { json: tool.schema.boolean().optional() },
  async execute(args, context) {
    const cmd = [py, script(context.worktree), "status"]
    if (args.json) cmd.push("--json")
    const p = Bun.spawn(cmd, { cwd: context.worktree, stdout: "pipe", stderr: "pipe" })
    const o = await new Response(p.stdout).text()
    const e = await new Response(p.stderr).text()
    const c = await p.exited
    if (c !== 0) throw new Error(e || `exit ${c}`)
    return o.trim()
  }
})