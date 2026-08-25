# MCP server (v1.7.0)

MCP Light Memory (formerly `internal-rag`) ships a minimal MCP-over-stdio server, compatible with Claude Code, Cursor, OpenCode, JetBrains, Warp, and the official `mcp` SDK.

For **multiple projects** through one connection, see [MCP-MULTI-PROJECT.md](MCP-MULTI-PROJECT.md) (`irag_mcp_router.py`).

## Dual-era protocol (v1.7.0)

The server supports both legacy and modern MCP protocol versions:

- **Legacy** (`2024-11-05`, `2025-03-26`, `2025-06-18`, `2025-11-25`): `initialize` / `notifications/initialized` / `tools/list` / `tools/call` / `ping` / `shutdown`. Backward compatible — existing clients unchanged.
- **Modern** (`2026-07-28`): `server/discover` (no `initialize` required), per-request `_meta`, `resultType: "complete"` envelopes, `structuredContent`, `outputSchema`, `ttlMs`/`cacheScope`. Legacy `initialize` still works for modern clients too.

## Tool annotations (v1.7.0)

Every tool carries `annotations`:
- `openWorldHint: false` — operates on local memory, not the open internet.
- `readOnlyHint` / `destructiveHint` / `idempotentHint` — match the tool's actual semantics.
- `search` and `context` update usage metadata in SQLite, so they are **not** marked `idempotent`.

## Structured content (v1.7.0)

`search`, `status`, `tasks`, `projects`, `guard` return `structuredContent` + `outputSchema` for modern clients. Legacy clients read `content` (TextContent) as before.

## Start

```bash
python3 .agents/skills/internal-rag/irag.py mcp
```

## Protocol

Minimal JSON-RPC 2.0 subset over stdin/stdout:

- `initialize` — handshake, returns `protocolVersion`, `serverInfo`.
  Negotiated versions: `2026-07-28` (modern), `2025-11-25`, `2025-06-18`,
  `2025-03-26`, `2024-11-05` (client's version when supported, else the
  latest legacy version).
- `notifications/initialized` — acknowledged (no response).
- `ping` — echoed.
- `shutdown` — exit cleanly.
- `tools/list` — list tools.
- `tools/call` — invoke a tool with `name` and `arguments`.

Stdout carries protocol messages only; logs go to stderr.

## Tools

| name | arguments | description |
|------|-----------|-------------|
| `context` | `task`, `limit?` | Context packet (WORKING_STATE, candidates, tokens, recovery) |
| `search` | `query`, `limit?` | BM25+MMR (embeddings if available) |
| `checkpoint` | `reason`, `phase?`, `completed?`, `in_progress?`, `blockers?`, `next?` | Save state |
| `guard` | — | Verify checkpoint freshness |
| `remember` | `type`, `title`, `body`, `tags?`, `evidence?`, `scope?`, `consequence?` | Store durable memory |
| `status` | — | Memory and checkpoint overview |
| `tasks` | — | Task stack |
| `resume` | — | Resume the top task |

## Claude Code config

In `claude_desktop_config.json` (or equivalent):

```json
{
  "mcpServers": {
    "internal-rag": {
      "command": "python3",
      "args": ["/abs/path/to/project/.agents/skills/internal-rag/irag.py", "mcp"],
      "cwd": "/abs/path/to/project"
    }
  }
}
```

On Windows use `python` instead of `python3` and backslash paths.

## Client config examples

Copy/paste configs for each client live in `examples/`:

| Client | Example file | Notes |
|--------|-------------|-------|
| Claude Code / Cursor | `examples/jetbrains.example.json` shape | `mcpServers` / `command` / `args` |
| Warp | `examples/warp.example.json` | uses `working_directory` |
| OpenCode V2 | `examples/opencode-v2.example.jsonc` | `mcp.servers.<name>` with `type: local`, `command` as array |
| OpenCode legacy | `examples/opencode-legacy.example.json` | `mcpServers` shape |
| JetBrains / PyCharm | `examples/jetbrains.example.json` | `mcpServers` / `command` / `args`; set **Working directory** in the JetBrains UI |
| Multi-project router | `examples/projects.example.json` | registry for `irag_mcp_router.py` |

### Windows vs Linux/macOS

- **Windows**: use `"command": "python"` (not `python3`); paths use backslashes or forward slashes (JSON accepts both).
- **Linux/macOS**: use `"command": "python3"`; paths use forward slashes.

### Single-project vs multi-project

- **Single project**: point the client at `irag.py mcp` with `cwd` = the project root.
- **Multi-project**: point the client at `irag_mcp_router.py --registry projects.json`. The router spawns an isolated `irag.py mcp` subprocess per call (`cwd=<project root>`), so projects never leak into each other.

### JetBrains AI Assistant note

JetBrains IDEs have a **built-in MCP Server** (the IDE acts as a server exposing IDE context to an external MCP client). That is the *opposite direction* from what INTERNAL_RAG uses (INTERNAL_RAG is a server the IDE's AI Assistant calls as a client). You do **not** need to enable the JetBrains built-in MCP Server to use INTERNAL_RAG — you add INTERNAL_RAG as an MCP server in the AI Assistant's `mcpServers` config.

## Troubleshooting

- **Server not found**: verify the absolute path to `irag.py` in `args`. Use forward slashes or escaped backslashes in JSON.
- **Wrong working directory (cwd)**: INTERNAL_RAG resolves ROOT from `cwd` (or git root). Set `cwd` / `working_directory` to the project root. In JetBrains, set Working directory in the MCP server UI.
- **Python executable not found**: use `python` on Windows, `python3` on Linux/macOS. Verify with `python --version` (3.8+).
- **Registry error (router)**: `write` must be a JSON boolean (`true`/`false`), not a string or int. `root` must be a string path. Project ids must be non-empty.
- **`write: false` blocks mutations**: a read-only project rejects `remember`/`checkpoint`/`resume` with a clear error. This is intentional (security boundary).

## Notes

- No external dependencies required (beyond optional embeddings).
- All calls operate on `INTERNAL_RAG/` in the current working directory (or git root).
- Errors are returned as JSON-RPC error objects (code -32000) or `isError: true` in `tools/call` results.
- The router does not strip `structuredContent` from child servers — modern clients receive it end-to-end.