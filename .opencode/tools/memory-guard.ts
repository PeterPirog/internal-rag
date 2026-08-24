import { tool } from "@opencode-ai/plugin"
const py = process.platform === "win32" ? "python" : "python3"
export default tool({description:"Verify no project-code changes are missing from the last checkpoint. Must pass before finishing.",args:{},async execute(_args,context){const s=`${context.worktree}/.agents/skills/internal-rag/irag.py`;const p=Bun.spawn([py,s,"guard"],{cwd:context.worktree,stdout:"pipe",stderr:"pipe"});const o=await new Response(p.stdout).text();const e=await new Response(p.stderr).text();await p.exited;return `${o}
${e}`.trim()}})
