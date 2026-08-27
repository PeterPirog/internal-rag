# Installation (short)

`install.py PROJECT` without `--client` only copies files — it does **not**
register the MCP server in any client. For a working Warp/OpenCode/JetBrains
setup, always pass the client and scope:

| You want (scope) | Command |
| --- | --- |
| Warp, project | `python install.py "C:\Projects\App" --client warp` |
| Warp, **global** client config | `python install.py "C:\Projects\App" --client warp --global` |
| OpenCode (stable/V1), project | `python install.py "C:\Projects\App" --client opencode` |
| OpenCode (stable/V1), global | `python install.py "C:\Projects\App" --client opencode --global` |
| OpenCode 2 (V2/beta), project | `python install.py "C:\Projects\App" --client opencode2` |
| OpenCode 2 (V2/beta), global | `python install.py "C:\Projects\App" --client opencode2 --global` |
| JetBrains/PyCharm, project | `python install.py "C:\Projects\App" --client jetbrains` (+ IDE UI step) |
| JetBrains/PyCharm, global | `python install.py "C:\Projects\App" --client jetbrains --global` (+ IDE UI step) |

Rules of thumb:

- **TARGET_PROJECT is always the first argument** — the directory the memory
  store must live in. Do not use `.` unless the current directory IS that
  project.
- `--global` = the **client config** scope (e.g. `~/.warp/.mcp.json`); the
  server still points at **this** project. It is NOT a multi-project router.
- "OpenCode" (no version) = `opencode` (V1). Only say `opencode2` for the
  beta/V2 runtime.
- JetBrains never auto-writes a config: the installer prints the JSON and the
  IDE menu path; the UI step is required.

Full guide (including the **Agent installation contract**): `docs/INSTALLATION.md`.
Linux/macOS: replace `python` with `python3`.
