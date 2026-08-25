# Zero-shot agent setup prompts

Copy-paste these prompts into your coding agent (Warp, OpenCode, PyCharm AI
Assistant, Claude Code, Cursor, or any MCP-capable client) to install and
configure **MCP Light Memory** automatically — no manual user steps required.

The agent will clone the repo, run the installer, register the MCP server in
its own config, and verify the setup. Everything is local; no cloud, no
daemon, no external service.

---

## Warp

```
Install and configure MCP Light Memory (mcp-light-memory) as an MCP server for this project, fully automatically.

Steps:
1. Clone the tool into a stable local location (do not put it inside the current project):
   - git clone https://github.com/PeterPirog/mcp-light-memory.git ~/mcp-light-memory
   - If ~/mcp-light-memory already exists, pull latest: git -C ~/mcp-light-memory pull --ff-only
2. Run the installer targeting the current project directory:
   - python ~/mcp-light-memory/install.py --target . --shared-tools
   - Use python3 on Linux/macOS, python on Windows.
   - If --shared-tools is not supported by this version, drop it.
3. Register the MCP server in Warp's MCP config:
   - Edit ~/.warp/mcp_servers.json (create it if missing).
   - Merge in this server entry (preserve any existing servers):
     {
       "mcpServers": {
         "mcp-light-memory": {
           "command": "python3",
           "args": ["<ABS_PATH_TO_CURRENT_PROJECT>/.agents/skills/internal-rag/mlm.py", "mcp"],
           "working_directory": "<ABS_PATH_TO_CURRENT_PROJECT>"
         }
       }
     }
   - On Windows use "python" instead of "python3" and backslash paths.
   - Replace <ABS_PATH_TO_CURRENT_PROJECT> with the real absolute path to this project.
4. Initialize the memory store in the current project:
   - python3 .agents/skills/internal-rag/mlm.py init
5. Verify:
   - python3 .agents/skills/internal-rag/mlm.py --version   # expect: 1.7.0
   - python3 .agents/skills/internal-rag/mlm.py status       # expect: INTERNAL_RAG ready
   - python3 .agents/skills/internal-rag/mlm.py guard        # expect: GUARD OK
6. Report a one-line success summary. If any step fails, print the exact error and stop.

Do not ask me any questions. Do not require manual editing. Do everything yourself and confirm at the end.
```

---

## OpenCode (V2 config)

```
Install and configure MCP Light Memory (mcp-light-memory) as an MCP server for this project, fully automatically.

Steps:
1. Clone the tool into a stable local location:
   - git clone https://github.com/PeterPirog/mcp-light-memory.git ~/mcp-light-memory
   - If ~/mcp-light-memory already exists: git -C ~/mcp-light-memory pull --ff-only
2. Install into the current project:
   - python ~/mcp-light-memory/install.py --target . --shared-tools
   - Use python3 on Linux/macOS, python on Windows. Drop --shared-tools if unsupported.
3. Register the MCP server in OpenCode's V2 config:
   - Edit opencode.json (or opencode.jsonc) in the current project root; create it if missing.
   - Merge in this server entry (preserve any existing keys):
     {
       "$schema": "https://opencode.ai/config.json",
       "mcp": {
         "servers": {
           "mcp-light-memory": {
             "type": "local",
             "command": ["python3", "<ABS_PATH_TO_CURRENT_PROJECT>/.agents/skills/internal-rag/mlm.py", "mcp"],
             "cwd": "<ABS_PATH_TO_CURRENT_PROJECT>"
           }
         }
       }
     }
   - On Windows use "python" instead of "python3" and backslash paths.
   - Replace <ABS_PATH_TO_CURRENT_PROJECT> with the real absolute path.
4. Initialize the memory store:
   - python3 .agents/skills/internal-rag/mlm.py init
5. Verify:
   - python3 .agents/skills/internal-rag/mlm.py --version   # expect: 1.7.0
   - python3 .agents/skills/internal-rag/mlm.py status       # expect: INTERNAL_RAG ready
   - python3 .agents/skills/internal-rag/mlm.py guard        # expect: GUARD OK
6. Report a one-line success summary. If any step fails, print the exact error and stop.

Do not ask me any questions. Do not require manual editing. Do everything yourself and confirm at the end.
```

---

## JetBrains AI Assistant / PyCharm

```
Install and configure MCP Light Memory (mcp-light-memory) as an MCP server for this project, fully automatically.

Steps:
1. Clone the tool into a stable local location:
   - git clone https://github.com/PeterPirog/mcp-light-memory.git ~/mcp-light-memory
   - If ~/mcp-light-memory already exists: git -C ~/mcp-light-memory pull --ff-only
2. Install into the current project:
   - python ~/mcp-light-memory/install.py --target . --shared-tools
   - Use python3 on Linux/macOS, python on Windows. Drop --shared-tools if unsupported.
3. Register the MCP server in JetBrains MCP config:
   - Edit ~/.config/jetbrains/mcp.json (create it if missing). On Windows: %USERPROFILE%\.jetbrains\mcp.json
   - Merge in this server entry (preserve any existing servers):
     {
       "mcpServers": {
         "mcp-light-memory": {
           "command": "python3",
           "args": ["<ABS_PATH_TO_CURRENT_PROJECT>/.agents/skills/internal-rag/mlm.py", "mcp"]
         }
       }
     }
   - On Windows use "python" instead of "python3" and backslash paths.
   - Replace <ABS_PATH_TO_CURRENT_PROJECT> with the real absolute path.
   - In the JetBrains UI, also set the Working Directory to the current project root (Settings > Tools > AI Assistant > MCP).
4. Initialize the memory store:
   - python3 .agents/skills/internal-rag/mlm.py init
5. Verify:
   - python3 .agents/skills/internal-rag/mlm.py --version   # expect: 1.7.0
   - python3 .agents/skills/internal-rag/mlm.py status       # expect: INTERNAL_RAG ready
   - python3 .agents/skills/internal-rag/mlm.py guard        # expect: GUARD OK
6. Report a one-line success summary. If any step fails, print the exact error and stop.

Do not ask me any questions. Do not require manual editing. Do everything yourself and confirm at the end.
```

---

## Multi-project router (any client)

```
Install and configure the MCP Light Memory multi-project router, fully automatically.

Steps:
1. Clone the tool if not already present:
   - git clone https://github.com/PeterPirog/mcp-light-memory.git ~/mcp-light-memory
   - If it exists: git -C ~/mcp-light-memory pull --ff-only
2. Create a projects registry at ~/mcp-light-memory-registry.json with the projects you want to expose:
   {
     "projects": {
       "<project-id>": { "root": "<ABS_PATH_TO_PROJECT_A>", "write": true },
       "<project-id-2>": { "root": "<ABS_PATH_TO_PROJECT_B>", "write": false }
     }
   }
   - Replace the ids and absolute paths with real values for the projects you want to route to.
   - Set write:false for read-only projects.
3. For EACH project in the registry, run the installer so INTERNAL_RAG/ exists:
   - python ~/mcp-light-memory/install.py --target <ABS_PATH_TO_PROJECT_A>
   - repeat for each project
4. Register the router as the MCP server in your client config (example for Warp):
   {
     "mcpServers": {
       "mcp-light-memory-router": {
         "command": "python3",
         "args": ["~/mcp-light-memory/.agents/skills/internal-rag/irag_mcp_router.py", "--registry", "~/mcp-light-memory-registry.json"],
         "working_directory": "~/mcp-light-memory"
       }
     }
   }
   - For OpenCode V2 use the "mcp.servers" shape with "type": "local" and command as an array.
   - For JetBrains use the "mcpServers" shape (set Working Directory in the UI).
   - On Windows use "python" and backslash paths.
5. Verify by calling the `projects` tool through the router — it should list all registered projects with availability=true.
6. Report a one-line success summary. If any step fails, print the exact error and stop.

Do not ask me any questions. Do not require manual editing. Do everything yourself and confirm at the end.
```

---

## Notes for the agent

- The installer (`install.py`) is idempotent — running it twice is safe.
- `mlm.py` is the primary CLI; `irag.py` is a legacy alias that still works.
- The on-disk folder is `INTERNAL_RAG/` (kept for backward compatibility — no rename needed).
- Zero required runtime dependencies: pure Python 3.8+ stdlib. Optional: `pip install sentence-transformers numpy` for better semantic retrieval.
- Everything runs locally over stdio; no cloud, no daemon, no HTTP.