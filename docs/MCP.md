# MCP server (v1.5.0)

INTERNAL_RAG ships a minimal MCP-over-stdio server, compatible with Claude Code, Cursor, OpenCode, JetBrains, Warp, and the official `mcp` SDK.

For **multiple projects** through one connection, see [MCP-MULTI-PROJECT.md](MCP-MULTI-PROJECT.md) (`irag_mcp_router.py`).

## Start

```bash
python3 .agents/skills/internal-rag/irag.py mcp
```

## Protocol

Minimal JSON-RPC 2.0 subset over stdin/stdout:

- `initialize` — handshake, returns `protocolVersion`, `serverInfo`.
  Negotiated versions: `2025-11-25`, `2025-06-18`, `2025-03-26`, `2024-11-05`
  (client's version when supported, else the latest).
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

## Notes

- No external dependencies required (beyond optional embeddings).
- All calls operate on `INTERNAL_RAG/` in the current working directory (or git root).
- Errors are returned as JSON-RPC error objects (code -32000).