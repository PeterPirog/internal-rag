import type { Plugin } from "@opencode-ai/plugin"
import { readFile } from "node:fs/promises"
import { join } from "node:path"
const py = process.platform === "win32" ? "python" : "python3"
export const InternalRagResilience: Plugin = async ({ worktree }) => {
  const script=join(worktree,".agents","skills","internal-rag","irag.py")
  const cp=async(reason:string,phase?:string)=>{try{const c=[py,script,"checkpoint","--reason",reason];if(phase)c.push("--phase",phase);const p=Bun.spawn(c,{cwd:worktree,stdout:"ignore",stderr:"ignore"});await p.exited}catch{}}
  return {
    "tool.execute.after": async (input,_output)=>{if(["edit","write","apply_patch"].includes(input.tool)) await cp(`opencode-auto-after-${input.tool}`)},
    event: async ({event})=>{if(event.type==="session.error") await cp("opencode-session-error","Session error; inspect prior output and Git state before continuing."); else if(event.type==="session.idle") await cp("opencode-session-idle")},
    "experimental.session.compacting": async (_input,output)=>{await cp("opencode-before-compaction","Context compaction; resume from persistent state.");let state="(unavailable)";try{state=await readFile(join(worktree,"INTERNAL_RAG","WORKING_STATE.md"),"utf8")}catch{};output.context.push(`\n## Persistent project memory\n${state}\nContinue using checkpoint/guard discipline.\n`)}
  }
}
