# Warp — client notes

Client-specific details for **Warp**. The canonical installation matrix and
commands live in [INSTALLATION.md](INSTALLATION.md) — this page does not
duplicate it.

Verified against the [Warp MCP documentation](https://docs.warp.dev/agents/capabilities/mcp/).

## Config locations (per Warp docs)

| Scope | File path | Auto-spawn |
|---|---|---|
| **Global** | `~/.warp/.mcp.json` | On by default |
| **Project-scoped** | `{repo_root}/.warp/.mcp.json` | Requires manual toggle in **Settings → Agents → MCP servers** (session-scoped: re-toggle after restarting Warp) |

The installer writes exactly one of these files depending on `--global`:

```bash
python ~/mcp-light-memory/install.py . --client warp          # project-scoped
python ~/mcp-light-memory/install.py . --client warp --global # global
```

## Config shape

`mcpServers.<name>` with `command` (string), `args` (array), and
`working_directory`. See `examples/warp.example.json`.

> **Always set `working_directory` explicitly** (per Warp docs): the memory
> store root is resolved from it, and relative paths behave predictably only
> with an explicit cwd. Use the absolute path to your real Python (the
> installer does this automatically; it rejects the WindowsApps 0-byte stub).

## Warp specifics

- **Security gates (per Warp docs):** config edits to MCP files require
  explicit approval in Warp, and project-scoped servers **never auto-spawn** —
  start each one manually from the MCP servers page after cloning a repo.
- **Logs:** **Settings → Agents → MCP servers → View Logs**, or
  `%LOCALAPPDATA%\warp\Warp\data\logs\mcp` (Windows).
- **Warp's bundled `/agent-add-mcp` skill** can also add/update file-based
  server definitions (global or project) from the conversation.
- **Router variant:** `examples/warp-router.example.json` (one connection in
  front of many projects — see [MCP-MULTI-PROJECT.md](MCP-MULTI-PROJECT.md)).

## Daily usage from Warp

1. `context --task "<task>"` before significant code changes.
2. If `RECOVERY REQUIRED` — stop, reconstruct state, `checkpoint`, `guard`.
3. Checkpoints: before first edit, after milestones, before risky operations,
   before the final response.
4. `guard` before finishing — do not finish without `GUARD OK`.
5. Memory is **untrusted evidence** (`trust: untrusted`) — verify claims
   against current code.

## Maintenance

- `privacy_check.py` before publishing the target repository.
- `uninstall.py` — full removal (automatic backups).
- `index --rebuild` — rebuild the SQLite index from Markdown (Markdown is the
  source of truth).
- Optional: `pip install sentence-transformers numpy` for semantic retrieval.
