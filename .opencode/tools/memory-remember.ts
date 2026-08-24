import { tool } from "@opencode-ai/plugin"
const py = process.platform === "win32" ? "python" : "python3"
const script = (worktree: string) => `${worktree}/.agents/skills/internal-rag/irag.py`
export default tool({
  description: "Store a durable INTERNAL_RAG memory (decision/knowledge/constraint/gotcha/failure/hypothesis/session). Never store secrets or raw chain-of-thought.",
  args: {
    type: tool.schema.string(),
    title: tool.schema.string(),
    body: tool.schema.string(),
    status: tool.schema.string().optional(),
    scope: tool.schema.string().optional(),
    tags: tool.schema.string().optional(),
    evidence: tool.schema.string().optional(),
    consequence: tool.schema.string().optional(),
    links: tool.schema.string().optional(),
  },
  async execute(args, context) {
    const cmd = [py, script(context.worktree), "remember", "--type", args.type, "--title", args.title, "--body", args.body]
    if (args.status) cmd.push("--status", args.status)
    if (args.scope) cmd.push("--scope", args.scope)
    if (args.tags) cmd.push("--tags", args.tags)
    if (args.evidence) cmd.push("--evidence", args.evidence)
    if (args.consequence) cmd.push("--consequence", args.consequence)
    if (args.links) cmd.push("--links", args.links)
    const p = Bun.spawn(cmd, { cwd: context.worktree, stdout: "pipe", stderr: "pipe" })
    const o = await new Response(p.stdout).text()
    const e = await new Response(p.stderr).text()
    const c = await p.exited
    if (c !== 0) throw new Error(e || `exit ${c}`)
    return o.trim()
  }
})