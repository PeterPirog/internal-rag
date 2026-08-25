# Zero-shot agent setup prompts

Copy-paste these prompts into your coding agent (Warp, OpenCode, PyCharm AI
Assistant, Claude Code, Cursor, or any MCP-capable client) to install and
configure **MCP Light Memory** automatically — no manual user steps required.

The agent will clone the repo, run the installer with `--client` (which
registers the MCP server in the correct config file), and verify the setup.
Everything is local; no cloud, no daemon, no external service.

> **Tip:** The installer auto-detects the Python interpreter (resolves
> `python` → `py` → `python3` to an absolute path) and writes it into the
> client config, so the MCP server starts reliably even when `python` is not
> in PATH on Windows.

---

## Warp

```
Install and configure MCP Light Memory (mcp-light-memory) as an MCP server for this project, fully automatically.

Steps:
1. Clone the tool into a stable local location (do not put it inside the current project):
   - git clone https://github.com/PeterPirog/mcp-light-memory.git ~/mcp-light-memory
   - If ~/mcp-light-memory already exists, pull latest: git -C ~/mcp-light-memory pull --ff-only
2. Run the installer targeting the current project directory with --client warp:
   - python ~/mcp-light-memory/install.py . --client warp
   - Use python3 on Linux/macOS, python on Windows.
   - The installer will: copy skill files, create INTERNAL_RAG/, create AGENTS.md, run init+checkpoint+validate, and register the MCP server in ~/.warp/.mcp.json (project-local by default; pass --global for the global config).
   - The installer writes the absolute path to the Python interpreter and the mlm.py script into the config, so Warp can start the server even if python is not in PATH.
3. Verify:
   - python .agents/skills/internal-rag/mlm.py --version   # expect: 1.7.0
   - python .agents/skills/internal-rag/mlm.py status       # expect: INTERNAL_RAG ready
   - python .agents/skills/internal-rag/mlm.py guard        # expect: GUARD OK
4. Report a one-line success summary. If any step fails, print the exact error and stop.

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
2. Run the installer targeting the current project directory with --client opencode:
   - python ~/mcp-light-memory/install.py . --client opencode
   - Use python3 on Linux/macOS, python on Windows.
   - The installer will register the MCP server in opencode.json (project root) with the "mcp.servers" shape and type: "local".
3. Verify:
   - python .agents/skills/internal-rag/mlm.py --version   # expect: 1.7.0
   - python .agents/skills/internal-rag/mlm.py status       # expect: INTERNAL_RAG ready
   - python .agents/skills/internal-rag/mlm.py guard        # expect: GUARD OK
4. Report a one-line success summary. If any step fails, print the exact error and stop.

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
2. Run the installer targeting the current project directory with --client jetbrains --global:
   - python ~/mcp-light-memory/install.py . --client jetbrains --global
   - Use python3 on Linux/macOS, python on Windows.
   - The installer will register the MCP server in ~/.jetbrains/mcp.json (global config).
   - In the JetBrains UI, also set the Working Directory to the current project root (Settings > Tools > AI Assistant > MCP).
3. Verify:
   - python .agents/skills/internal-rag/mlm.py --version   # expect: 1.7.0
   - python .agents/skills/internal-rag/mlm.py status       # expect: INTERNAL_RAG ready
   - python .agents/skills/internal-rag/mlm.py guard        # expect: GUARD OK
4. Report a one-line success summary. If any step fails, print the exact error and stop.

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
   - python ~/mcp-light-memory/install.py <ABS_PATH_TO_PROJECT_A>
   - repeat for each project
4. Register the router as the MCP server in your client config (example for Warp):
   {
     "mcpServers": {
       "mcp-light-memory-router": {
         "command": "<ABS_PATH_TO_PYTHON>",
         "args": ["<ABS_PATH_TO_MCP_LIGHT_MEMORY>/.agents/skills/internal-rag/irag_mcp_router.py", "--registry", "<ABS_PATH_TO_REGISTRY>"],
         "working_directory": "<ABS_PATH_TO_MCP_LIGHT_MEMORY>"
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

## Uninstall / unregister

To remove the MCP server registration from a client config (without removing
the memory data):

```
python ~/mcp-light-memory/install.py . --client warp --unregister
python ~/mcp-light-memory/install.py . --client opencode --unregister
python ~/mcp-light-memory/install.py . --client jetbrains --global --unregister
```

For a full uninstall (removes skill files, AGENTS.md section, git excludes,
manifest — but preserves INTERNAL_RAG/ memory data), use `uninstall.py`:

```
python ~/mcp-light-memory/uninstall.py .
```

---

## Notes for the agent

- The installer (`install.py`) is idempotent — running it twice is safe.
- `--client <warp|opencode|jetbrains>` registers the MCP server automatically; no manual config editing needed.
- `--global` uses the client's global config; without it, project-local config is used.
- `mlm.py` is the primary CLI; `irag.py` is a legacy alias that still works.
- The on-disk folder is `INTERNAL_RAG/` (kept for backward compatibility — no rename needed).
- Zero required runtime dependencies: pure Python 3.8+ stdlib. Optional: `pip install sentence-transformers numpy` for better semantic retrieval.
- Everything runs locally over stdio; no cloud, no daemon, no HTTP.