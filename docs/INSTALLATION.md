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

### Registration outcome & exit code (agent contract)

`install.py` reports the MCP registration outcome explicitly:

- `MCP REGISTRATION: REGISTERED <path>` — the client config was written.
- `MCP REGISTRATION: MANUAL_REQUIRED` + `PROJECT FILES INSTALLED` /
  `MCP REGISTRATION NOT COMPLETE` / `MANUAL ACTION REQUIRED` — the installer
  refused to guess (e.g. only `opencode.jsonc` exists); perform the printed
  manual edit.
- `MCP REGISTRATION: INSTRUCTIONS_ONLY` — JetBrains/PyCharm: assisted by
  design; the IDE UI step is required.

Exit codes: `0` = requested automatic registration completed, or the client is
explicitly manual (JetBrains); `2` = `MANUAL_REQUIRED` (automatic registration
was requested but could not be completed). Project files are installed in all
cases.

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

Manual setup in the IDE (per JetBrains docs). The installer **never writes a
JetBrains config file** — it prints the ready-to-paste JSON and the IDE menu
path. The printed **Server level** matches the scope you requested:

1. `install.py . --client jetbrains` → printed instruction: **Server level: Project / Current project**
2. `install.py . --client jetbrains --global` → printed instruction: **Server level: Global**

UI steps (per JetBrains docs):

1. Settings (`Ctrl+Alt+S`) → **Tools** → **AI Assistant** → **Model Context Protocol (MCP)** → **Add** → **STDIO**.
2. Paste the JSON the installer printed (`examples/jetbrains.example.json` shows the shape: `mcpServers.<name>` with `command` + `args`).
3. **Working directory**: the project root (critical — the memory store is created under the cwd).
4. **Server level**: as printed by the installer (Project, or Global with `--global`).
5. OK → Apply; green status = connected. Logs: Help → Show Log in Explorer → `mcp/`.

Do not describe this as "fully automatic" — the UI step is required.

## Existing config files: fail-closed handling

The installer **never overwrites or "repairs" a client config it cannot
parse**. If the target config (Warp/OpenCode/OpenCode2) exists and is not
valid JSON — or its `mcp` / `mcpServers` container is not a JSON object — the
installer:

- stops with a clear `ERROR` containing the config path and the parser error;
- leaves the file **byte-for-byte unchanged**;
- makes no attempt to fix arbitrary malformed content.

Fix the file manually (or back it up first), then re-run the installer.

### OpenCode JSONC

OpenCode officially supports JSONC (JSON with Comments). The automatic write
path is the plain `opencode.json` file. If the project/global location has an
`opencode.jsonc` (but no `opencode.json`), the installer does **not** guess
at a JSONC merge: it fails safely and prints the precise manual edit
(file, placement, snippet) to make in `opencode.jsonc` instead of risking
config loss.

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

## Agent installation contract

Deterministic rules for agents (Warp / OpenCode / any CLI agent) that must
translate a natural-language request into an exact `install.py` invocation.
Do not guess — apply these rules in order.

### 1. TARGET_PROJECT (first argument, always)

- If the user gives a project path (e.g. `C:\Projects\App`), **always** use it
  as the first argument to `install.py`.
- Never use `.` unless `git rev-parse --show-toplevel` confirms the current
  working directory **is** the target project.
- All `mlm.py` verification commands must run with **cwd = TARGET_PROJECT**
  (or `Push-Location` / `cd` equivalent).

### 2. CLIENT (deterministic mapping, no version guessing)

| User says | Flag |
|---|---|
| "Warp" | `--client warp` |
| "OpenCode", "OpenCode stable", "OpenCode V1" | `--client opencode` |
| "OpenCode 2", "OpenCode V2", "opencode2", "OpenCode beta" | `--client opencode2` |
| "PyCharm", "JetBrains AI Assistant" | `--client jetbrains` |

OpenCode V1 runs as `opencode`; OpenCode 2 runs as a separate `opencode2`.
If the requesting agent **is** the OpenCode 2 runtime itself, that runtime
selects `opencode2`. Otherwise map by the words above — never guess a version.

### 3. SCOPE

- "project", "for this project", or "for project C:\X" without "global" → **no** `--global`.
- "global" or "globally" → `--global`.
- **"globally for project C:\X"** means: global **client config**, server
  bound to `C:\X`. It does **NOT** mean the multi-project router.
- Choose the router only when the user explicitly says "multiple projects",
  "multi-project", "one endpoint for several repositories", or lists several
  projects.

### 4. Exact examples

| Request | Command |
|---|---|
| "Install the mcp-light-memory server in Warp globally for project C:\Work\App" | `python <tool>/install.py "C:\Work\App" --client warp --global` |
| "Install mcp-light-memory for OpenCode for project C:\Work\App" | `python <tool>/install.py "C:\Work\App" --client opencode` |
| "Install for OpenCode 2, global, for project C:\Work\App" | `python <tool>/install.py "C:\Work\App" --client opencode2 --global` |
| "Prepare mcp-light-memory for PyCharm globally for project C:\Work\App" | `python <tool>/install.py "C:\Work\App" --client jetbrains --global` + manual JetBrains UI step (Server level = Global) |

### 5. Agent workflow

a. verify TARGET_PROJECT exists and is a Git repo;
b. clone/pull `mcp-light-memory` once into a **stable location outside** the
   target project (e.g. `~/mcp-light-memory`);
c. run the exact `install.py` with client + scope + target from above;
d. **never** reset or force-overwrite an existing client config — the
   installer is fail-closed on unparseable configs and preserves valid ones;
e. verify **with cwd = TARGET_PROJECT**:
   `mlm.py --version`, `mlm.py status`, `mlm.py guard`;
f. for Warp/OpenCode, confirm the target config file contains
   `mcp-light-memory` **and** the target project path;
g. report success **only after** the real registration is confirmed;
h. if a final step needs UI/approval, say so explicitly.

### 6. Warp: config vs activation

Writing the Warp config is automatic. Project-scoped Warp servers may still
require activation/approval inside the client (toggle in Warp settings) —
do not describe project-scoped Warp as unconditionally "fully automatic".

### 7. OpenCode JSONC

If the installer prints **MANUAL EDIT REQUIRED (JSONC)** for an existing
`opencode.jsonc`, the MCP install is **not** complete. Perform a safe manual
edit if you have file-editing tools; otherwise clearly report
"manual action required" and stop.

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
