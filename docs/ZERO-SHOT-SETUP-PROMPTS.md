# Zero-shot agent setup prompts

Copy-paste these prompts into your coding agent (Warp, OpenCode, PyCharm AI
Assistant, Claude Code, Cursor, or any MCP-capable client) to install and
configure **MCP Light Memory**. The commands below are the canonical
installation contract — see [INSTALLATION.md](INSTALLATION.md) for the full
matrix and manual setups. The canonical version is the `VERSION` file; never
hard-code an expected version number.

> **Tip:** The installer auto-detects the Python interpreter (resolves
> `python` → `py` → `python3` to an absolute path) and writes it into the
> client config, so the MCP server starts reliably even when `python` is not
> in PATH on Windows.

> **Warp project scope:** writing `{repo}/.warp/.mcp.json` is automatic, but
> Warp may still require project-scoped activation/approval in the client.
> Treat config registration and client activation as two separate outcomes;
> never claim activation completed if Warp still asks for a toggle/approval.

> **OpenCode JSONC safety:** if `install.py` reports
> `MCP REGISTRATION: MANUAL_REQUIRED` (exit code `2`), for example because an
> existing `opencode.jsonc` must be preserved, the MCP registration is **not
> complete**. Perform the printed safe JSONC edit if your agent has file-editing
> tools; otherwise report the exact manual action required. Never replace the
> user's JSONC with a second config just to force an automatic success.

> **JetBrains/PyCharm is assisted, not fully automatic:** the installer
> prepares the JSON and Working Directory, but the final registration happens
> in the IDE UI (Settings → Tools → AI Assistant → MCP) — the agent cannot
> complete that step for you.

---

## Warp

```
Install and configure MCP Light Memory (mcp-light-memory) as an MCP server for this project. Perform every safe automatic step yourself.

Steps:
1. Clone the tool into a stable local location (do not put it inside the current project):
   - git clone https://github.com/PeterPirog/mcp-light-memory.git ~/mcp-light-memory
   - If ~/mcp-light-memory already exists, pull latest: git -C ~/mcp-light-memory pull --ff-only
2. Run the installer targeting the current project directory:
   - python ~/mcp-light-memory/install.py . --client warp
   - Use python3 on Linux/macOS, python on Windows.
   - The installer will: copy skill files, create INTERNAL_RAG/, create AGENTS.md, run init+checkpoint+validate, and register the MCP server in the project config {repo}/.warp/.mcp.json (pass --global to register in ~/.warp/.mcp.json instead).
   - The installer writes the absolute path to the Python interpreter, args, and working_directory into the config.
   - Continue only if the installer reports MCP REGISTRATION: REGISTERED.
3. Verify:
   - python .agents/skills/internal-rag/mlm.py --version   # reports the installed version (see the VERSION file)
   - python .agents/skills/internal-rag/mlm.py status       # expect: INTERNAL_RAG ready
   - python .agents/skills/internal-rag/mlm.py guard        # expect: GUARD OK
   - Verify the selected Warp config contains mcp-light-memory and the current project path.
4. If Warp requires a project-scoped activation/toggle/approval after the config is written, report that exact client-side step. Do not claim the server is active until that step is completed.
5. Report a one-line success summary only when registration and verification are complete. If any step fails, print the exact error and stop.

Do not ask me unnecessary questions. Do not require manual config editing for Warp. Complete all safe automatic steps yourself; report any Warp activation/approval separately if the client still requires it.
```

---

## OpenCode stable (V1)

```
Install and configure MCP Light Memory (mcp-light-memory) as an MCP server for this project. Complete the registration automatically when the existing config can be updated safely.

Steps:
1. Clone the tool into a stable local location:
   - git clone https://github.com/PeterPirog/mcp-light-memory.git ~/mcp-light-memory
   - If it exists: git -C ~/mcp-light-memory pull --ff-only
2. Run the installer targeting the current project directory:
   - python ~/mcp-light-memory/install.py . --client opencode
   - Use python3 on Linux/macOS, python on Windows.
   - The installer registers the MCP server in opencode.json (project root) with the flat V1 shape: mcp.<name> with type "local", command as an array, cwd, and enabled: true. Pass --global to write ~/.config/opencode/opencode.json instead.
   - If the installer reports MCP REGISTRATION: REGISTERED, continue to verification.
   - If it reports MCP REGISTRATION: MANUAL_REQUIRED (exit code 2), do NOT claim success. If you can safely edit the existing opencode.jsonc while preserving comments and unrelated settings, perform the printed edit and verify it. Otherwise report the exact manual action required and stop.
3. Verify from the target project directory:
   - python .agents/skills/internal-rag/mlm.py --version   # reports the installed version (see the VERSION file)
   - python .agents/skills/internal-rag/mlm.py status       # expect: INTERNAL_RAG ready
   - python .agents/skills/internal-rag/mlm.py guard        # expect: GUARD OK
   - Verify the selected OpenCode config contains mcp-light-memory and the target project path.
4. Report a one-line success summary only after real MCP registration is confirmed. If any step fails, print the exact error and stop.

Do not overwrite or replace an existing config just to force success. Complete safe edits yourself when possible; if MANUAL_REQUIRED cannot be resolved safely, report it explicitly instead of claiming the MCP server is installed.
```

---

## OpenCode 2 (V2, beta)

```
Install and configure MCP Light Memory (mcp-light-memory) as an MCP server for this project using OpenCode 2 / V2. Complete the registration automatically when the existing config can be updated safely.

Steps:
1. Clone: git clone https://github.com/PeterPirog/mcp-light-memory.git ~/mcp-light-memory
   (if it exists: git -C ~/mcp-light-memory pull --ff-only)
2. Install: python ~/mcp-light-memory/install.py . --client opencode2
   (use python3 on Linux/macOS)
   The installer writes opencode.json with the V2 shape: mcp.servers.<name> with type: local, command as an array, cwd — and NO 'enabled' field (V2 disables via 'disabled'). Pass --global to write ~/.config/opencode/opencode.json instead.
   - If the installer reports MCP REGISTRATION: REGISTERED, continue to verification.
   - If it reports MCP REGISTRATION: MANUAL_REQUIRED (exit code 2), do NOT claim success. If you can safely edit the existing opencode.jsonc while preserving comments and unrelated settings, perform the printed V2 edit and verify it. Otherwise report the exact manual action required and stop.
3. Optionally add compaction integration: python ~/mcp-light-memory/install.py . --client opencode2 --compaction
   - If JSONC is manual-only, do not create a second opencode.json; follow the installer's safe/manual guidance.
4. Verify from the target project directory:
   - python .agents/skills/internal-rag/mlm.py --version  # reports the installed version, see the VERSION file
   - python .agents/skills/internal-rag/mlm.py status
   - python .agents/skills/internal-rag/mlm.py guard      # expect GUARD OK
   - Verify the selected OpenCode config contains mcp-light-memory and the target project path.
5. Report success only after real MCP registration is confirmed. If any step fails, print the exact error and stop.

Do not overwrite or replace an existing config just to force success. Complete safe edits yourself when possible; if MANUAL_REQUIRED cannot be resolved safely, report it explicitly instead of claiming the MCP server is installed.
```

---

## JetBrains AI Assistant / PyCharm (assisted setup)

The final step is done by YOU in the IDE UI — no agent can do it.

```
Prepare MCP Light Memory (mcp-light-memory) as an MCP server for this project.

Steps:
1. Clone the tool into a stable local location:
   - git clone https://github.com/PeterPirog/mcp-light-memory.git ~/mcp-light-memory
   - If it exists: git -C ~/mcp-light-memory pull --ff-only
2. Run the installer targeting the current project directory:
   - python ~/mcp-light-memory/install.py . --client jetbrains
   - Use python3 on Linux/macOS, python on Windows.
   - The installer copies the skill files, creates INTERNAL_RAG/, runs init+checkpoint+validate, and PRINTS a ready-to-paste JSON block plus the Working Directory. It does NOT write any config file — PyCharm manages MCP servers exclusively in its UI.
3. Verify:
   - python .agents/skills/internal-rag/mlm.py --version   # reports the installed version (see the VERSION file)
   - python .agents/skills/internal-rag/mlm.py status       # expect: INTERNAL_RAG ready
   - python .agents/skills/internal-rag/mlm.py guard        # expect: GUARD OK
4. Then tell me EXACTLY where to finish in the IDE:
   - Settings (Ctrl+Alt+S) -> Tools -> AI Assistant -> Model Context Protocol (MCP) -> Add -> STDIO
   - paste the JSON block from step 2
   - Working Directory = the current project root (required — the memory store is created under this cwd)
   - Server level = Project or Global (my choice; a global server still points at THIS project)
   - OK -> Apply; green status = connected
```

---

## Multi-project router (any client)

If you need **one global MCP endpoint for many repositories** (a single
`--global` registration only ever points at one target project), use the
multi-project router — see [MCP-MULTI-PROJECT.md](MCP-MULTI-PROJECT.md).

```
Install and configure the MCP Light Memory multi-project router. Perform every safe automatic step yourself; if the selected client requires UI/approval/manual config work, report that boundary explicitly instead of claiming unconditional completion.

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
   - Replace the ids and absolute paths with real values.
   - Set write:false for read-only projects.
3. For EACH project in the registry, run the installer so INTERNAL_RAG/ exists:
   - python ~/mcp-light-memory/install.py <ABS_PATH_TO_PROJECT_A>
   - repeat for each project
4. Register the router as the MCP server in your client config (see examples/warp-router.example.json and examples/opencode-v2-router.example.jsonc):
   - Warp: mcpServers shape with command/args/working_directory.
   - OpenCode V1: flat mcp.<name> with type local, command array, enabled: true.
   - OpenCode V2: mcp.servers.<name> with type local, command array, no enabled field.
   - JetBrains: paste in the IDE UI (STDIO), set Working Directory, choose Server level.
5. Verify by calling the `projects` tool through the router — it should list all registered projects with available=true.
6. Report a one-line success summary only after the selected client's actual registration/activation boundary has been satisfied. If any step fails, print the exact error and stop.

Do not reset or overwrite unrelated client config. Complete safe automatic edits yourself; when the client requires a UI/approval/manual step, report it explicitly.
```

---

## Uninstall / unregister

To remove the MCP server registration from a client config (without removing
the memory data):

```
python ~/mcp-light-memory/install.py . --client warp --unregister
python ~/mcp-light-memory/install.py . --client opencode --unregister
python ~/mcp-light-memory/install.py . --client opencode2 --unregister
python ~/mcp-light-memory/install.py . --client jetbrains --unregister
```

(For JetBrains the command only prints where to remove the server in the IDE.)

For a full uninstall (removes skill files, AGENTS.md section, git excludes,
manifest — but preserves INTERNAL_RAG/ memory data), use `uninstall.py`:

```
python ~/mcp-light-memory/uninstall.py .
```

---

## Notes for the agent

- The installer (`install.py`) is idempotent — running it twice is safe.
- `--client <warp|opencode|opencode2|jetbrains>` registers the MCP server when the selected config can be updated safely (JetBrains: prints setup instructions; it never writes a config file).
- `MCP REGISTRATION: REGISTERED` means the automatic client-config write completed; `MANUAL_REQUIRED` means it did not and must not be reported as success.
- Warp project-scope config registration can still require a client-side activation/toggle/approval.
- `--global` uses the client's **global config file**; the server still points at the target project you installed into.
- `mlm.py` is the primary CLI; `irag.py` is a legacy alias that still works.
- The on-disk folder is `INTERNAL_RAG/` (kept for backward compatibility — no rename needed).
- Zero required runtime dependencies: pure Python 3.8+ stdlib. Optional: `pip install sentence-transformers numpy` for better semantic retrieval.
- Everything runs locally over stdio; no cloud, no daemon, no HTTP.
