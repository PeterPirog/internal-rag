# Multi-project MCP (v1.6.0)

One MCP server in front of many INTERNAL_RAG projects.

INTERNAL_RAG is **per-project** by design: every project has its own
`INTERNAL_RAG/` memory and its own `irag.py mcp` stdio server that resolves
ROOT from the working directory. The router lets a single MCP client
(Claude Code, Cursor, OpenCode, the official `mcp` SDK, …) reach several of
those projects through one connection, without any project ever seeing
another's memory.

## Start

```bash
python .agents/skills/internal-rag/irag_mcp_router.py --registry /path/to/projects.json
```

The registry is a plain JSON file (see `examples/projects.example.json`):

```json
{
  "projects": {
    "my-app":     { "root": "../my-app",           "write": true },
    "shared-lib": { "root": "C:/repos/shared-lib", "write": false }
  }
}
```

- `root` — project directory (may be relative to the registry file). Must
  contain an `INTERNAL_RAG/`.
- `write` — `true` allows mutating tools (`remember`, `checkpoint`, `resume`);
  `false` blocks them with a clear, structured error. Default is `false`.

## Tools

Every project-scoped tool takes a required `project` parameter (a registered
id). There is also a router-level `projects` tool.

| name | project? | mutating | description |
|------|:-------:|:--------:|-------------|
| `projects` | no | no | List registered projects with `root`, `write`, `available`, `reason` |
| `context` | yes | no | Context packet for the named project |
| `search` | yes | no | Search durable memories (read-only) |
| `guard` | yes | no | Verify the project's checkpoint freshness |
| `status` | yes | no | Memory + checkpoint status |
| `tasks` | yes | no | Show the task stack |
| `remember` | yes | **yes** | Store durable memory (blocked when `write:false`) |
| `checkpoint` | yes | **yes** | Persist state (blocked when `write:false`) |
| `resume` | yes | **yes** | Pop/resume the top task (blocked when `write:false`) |

## Isolation model

- **Subprocess per call.** Each `tools/call` is executed in a fresh
  `irag.py mcp` subprocess started with `cwd=<project root>`. Because
  `irag.py` resolves ROOT from the cwd, a child can only see that one
  project's `INTERNAL_RAG/`. No in-process state is shared between projects.
- **Allowlist.** Only ids present in the registry are routable. Any other id
  returns `unknown project: 'x'. Registered projects: …`.
- **Write gate.** Mutating tools are rejected **before** any subprocess is
  spawned when `write:false`, so a read-only project can never be modified
  even if its on-disk permissions would allow it.
- **Availability.** A project whose `root` is missing or lacks `INTERNAL_RAG/`
  is reported `available:false` by `projects` and yields an actionable
  error (`run `irag.py init` there`) if called.

## Client config

In `claude_desktop_config.json` / Cursor / OpenCode MCP settings:

```json
{
  "mcpServers": {
    "internal-rag-router": {
      "command": "python3",
      "args": [
        "/abs/path/to/internal-rag/.agents/skills/internal-rag/irag_mcp_router.py",
        "--registry", "/abs/path/to/projects.json"
      ]
    }
  }
}
```

On Windows use `python` and Windows paths.

## Single-project (no router)

For one project, keep using the direct server — it is what the router
spawns under the hood:

```bash
python .agents/skills/internal-rag/irag.py mcp
```

## Guarantees

- **Zero required dependencies.** The router is stdlib-only (Python 3.8+).
- **Pure stdout.** Protocol messages only on stdout; logs on stderr.
- **Negotiated protocol versions:** `2026-07-28` (modern), `2025-11-25`,
  `2025-06-18`, `2025-03-26`, `2024-11-05` (client's version when supported,
  else the latest legacy version).
- **No project can leak into another** — verified by
  `tests/test_mcp_router.py::test_isolation_between_projects` and
  `tests/test_mcp_sdk_compat.py`.
