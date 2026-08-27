# Installation

Canonical installation guide for **MCP Light Memory**. This is the single
source of truth for "which client, which scope, which command". The canonical
version is defined by the `VERSION` file (see it — do not hard-code version
expectations in your notes or prompts).

## Requirements

```text
python --version   # 3.8+
git --version
```

The target project should be a Git repository (required for fingerprinting,
recovery detection, and checkpoints).

Clone the tool once into a stable location *outside* the project:

```bash
git clone https://github.com/PeterPirog/mcp-light-memory.git ~/mcp-light-memory
```

## What the installer does

```bash
python ~/mcp-light-memory/install.py <target-project> --client <client> [--global]
```

- copies the skill + CLI (`mlm.py` primary, `irag.py` legacy alias) into the target project,
- creates `INTERNAL_RAG/` and runs `init` + `checkpoint` + `validate` (so `guard` is `OK` immediately),
- updates only the marked section of `AGENTS.md`,
- configures `.git/info/exclude` (memory + integration files stay local; `--share-tools` changes this),
- registers the MCP server in the client config (or prints manual instructions for JetBrains),
- writes the **absolute path** to the verified Python interpreter (survives Windows PATH issues).

The installer is idempotent — re-running it updates in place and preserves
existing memory.

## Installation matrix

| Client | Scope | Command |
|---|---|---|
| **Warp** | automatic, project | `install.py . --client warp` |
| **Warp** | automatic, global | `install.py . --client warp --global` |
| **Warp** | manual, project | paste JSON into Settings → Agents → MCP (writes/edits `{repo}/.warp/.mcp.json`) |
| **Warp** | manual, global | paste JSON (writes/edits `~/.warp/.mcp.json`) |
| **OpenCode stable (V1)** | automatic, project | `install.py . --client opencode` |
| **OpenCode stable (V1)** | automatic, global | `install.py . --client opencode --global` |
| **OpenCode stable (V1)** | manual, project | add flat `mcp.<name>` entry to project `opencode.json` |
| **OpenCode stable (V1)** | manual, global | add flat `mcp.<name>` entry to `~/.config/opencode/opencode.json` |
| **OpenCode 2 (V2, beta)** | automatic, project | `install.py . --client opencode2` |
| **OpenCode 2 (V2, beta)** | automatic, global | `install.py . --client opencode2 --global` |
| **OpenCode 2 (V2, beta)** | manual, project | add `mcp.servers.<name>` entry to project `opencode.json` |
| **OpenCode 2 (V2, beta)** | manual, global | add `mcp.servers.<name>` entry to `~/.config/opencode/opencode.json` |
| **JetBrains AI / PyCharm** | manual, project | `install.py . --client jetbrains` → IDE UI: Server level = **Project** |
| **JetBrains AI / PyCharm** | manual, global | `install.py . --client jetbrains --global` → IDE UI: Server level = **Global** |

JetBrains has **no automatic registration**: the IDE manages MCP servers
exclusively through its UI (Settings → Tools → AI Assistant → MCP). The
installer prepares the ready-to-paste JSON and the Working Directory — that is
the limit of what can be automated.

### Warp config shape

`mcpServers.<name>` with `command` (string), `args` (array), and
`working_directory` (always set it explicitly):

```json
{
  "mcpServers": {
    "mcp-light-memory": {
      "command": "python",
      "args": ["<abs>/project/.agents/skills/internal-rag/mlm.py", "mcp"],
      "working_directory": "<abs>/project"
    }
  }
}
```

See `examples/warp.example.json` and `docs/WARP-SETUP.md` for client details
(auto-spawn behavior, logs, project toggle).

### OpenCode stable (V1) config shape

Servers are **flat** under `mcp.<name>` (no `servers` sub-key) and use
`enabled: true`. `command` is an array:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "mcp-light-memory": {
      "type": "local",
      "command": ["python", "<abs>/project/.agents/skills/internal-rag/mlm.py", "mcp"],
      "cwd": "<abs>/project",
      "enabled": true
    }
  }
}
```

See `examples/opencode-legacy.example.json` and `docs/OPENCODE.md`.

### OpenCode 2 (V2, beta) config shape

Servers live under `mcp.servers.<name>`, `command` is an array, and there is
**no `enabled` field** (V2 disables via `disabled: true`, absent = enabled):

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "mcp-light-memory": {
        "type": "local",
        "command": ["python", "<abs>/project/.agents/skills/internal-rag/mlm.py", "mcp"],
        "cwd": "<abs>/project"
      }
    }
  }
}
```

See `examples/opencode-v2.example.jsonc` and `docs/OPENCODE.md` (also covers
the resilience plugin API per version).

### JetBrains AI Assistant / PyCharm

Manual setup in the IDE (per JetBrains docs):

1. Settings (`Ctrl+Alt+S`) → **Tools** → **AI Assistant** → **Model Context Protocol (MCP)** → **Add** → **STDIO**.
2. Paste the JSON the installer printed (`examples/jetbrains.example.json` shows the shape: `mcpServers.<name>` with `command` + `args`).
3. **Working directory**: the project root (critical — the memory store is created under the cwd).
4. **Server level**: **Project** or **Global** (both are IDE-level choices; the installer does not set them).
5. OK → Apply; green status = connected. Logs: Help → Show Log in Explorer → `mcp/`.

Do not describe this as "fully automatic" — the UI step is required.

## `--global` semantics

**`--global` changes the scope of the CLIENT CONFIG, not the server's
project binding.**

- `install.py . --client warp --global` writes `~/.warp/.mcp.json` instead of
  `{repo}/.warp/.mcp.json`. The registered server still points at **this**
  target project (`cwd` / `working_directory` = the project you installed into).
- For OpenCode: `--global` writes `~/.config/opencode/opencode.json` instead of
  the project's `opencode.json`. Same binding.
- For JetBrains: `--global` only hints the IDE's *Global* server level; you
  still choose it in the UI.

**Consequence:** one `--global` registration serves exactly one project.
If you need **one global MCP endpoint for many repositories**, use the
multi-project router — see [MCP-MULTI-PROJECT.md](MCP-MULTI-PROJECT.md).

## Client-specific notes

- **Warp** — file-based servers auto-spawn when global; project-scoped
  servers require a manual toggle (see `docs/WARP-SETUP.md`).
- **OpenCode** — the installer also copies exactly one resilience plugin
  (V1 or V2) plus native tools/commands (see `docs/OPENCODE.md`).
  `--compaction` optionally merges compaction settings.
- **JetBrains/PyCharm** — assisted setup only (see above).

## Uninstall / unregister

```bash
python ~/mcp-light-memory/install.py . --client <warp|opencode|opencode2|jetbrains> --unregister
```

Removes only the MCP registration (JetBrains: prints where to remove it in the
IDE). Full removal: `python ~/mcp-light-memory/uninstall.py .`
(see `docs/UNINSTALL.md`).

## Optional extras

- **Embeddings:** `pip install -r requirements-optional.txt`, then
  `retrieval.embeddings: auto` in `.irag.yml` (see `docs/EMBEDDINGS.md`).
- **Git hooks:** `python .agents/skills/internal-rag/irag_hooks.py install`
  (see `docs/GIT-HOOKS.md`).
- **MCP details:** `docs/MCP.md`. **Multi-project:** `docs/MCP-MULTI-PROJECT.md`.

## Update

Run the new `install.py` on the same project. Existing `WORKING_STATE.md`
and memory directories are preserved.

## Zero-shot prompts

Agent-ready prompts for each client: [ZERO-SHOT-SETUP-PROMPTS.md](ZERO-SHOT-SETUP-PROMPTS.md).
