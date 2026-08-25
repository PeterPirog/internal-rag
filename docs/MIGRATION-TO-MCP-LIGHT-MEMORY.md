# Migration: internal-rag → MCP Light Memory

This document explains how the rebrand from **internal-rag** to **MCP Light Memory** affects you and what (if anything) you need to update.

## TL;DR

- **Nothing breaks.** Your existing `INTERNAL_RAG/` data, `irag.py` scripts, and MCP client configs continue to work.
- The new primary CLI is `mlm` (`mlm.py`); `irag.py` remains a supported legacy alias.
- The new product name is **MCP Light Memory** (`mcp-light-memory`); old MCP server names in configs keep working but are deprecated.
- No data migration is required. The on-disk folder `INTERNAL_RAG/` is kept as the durable compatibility storage location.

## Name mapping

| Old | New | Status |
|---|---|---|
| `internal-rag` (product) | `MCP Light Memory` | Old name deprecated; new name primary. |
| `irag.py` (CLI module) | `mlm.py` (CLI shim) | `irag.py` kept as a legacy alias; `mlm.py` is primary. |
| `irag` (CLI command) | `mlm` (CLI command) | Both work; `mlm` is preferred in docs. |
| `INTERNAL_RAG/` (storage) | `INTERNAL_RAG/` (unchanged) | **No change.** Kept for backward compatibility. |
| `internal-rag` (MCP server name) | `mcp-light-memory` | Old name still works in client configs; new name preferred. |
| `internal-rag-router` (router name) | `mcp-light-memory-router` | Old name still works; new name preferred. |
| `<!-- INTERNAL_RAG_START -->` (AGENTS.md markers) | `<!-- MCP_LIGHT_MEMORY_START -->` | `install.py` writes the new markers; old markers are migrated on next install. |

## What you should update (recommended, not required)

1. **MCP client configs** — rename the server key from `internal-rag` to `mcp-light-memory` for clarity. The command path (`.agents/skills/internal-rag/irag.py`) still works; you may switch to `mlm.py` if you prefer. See `examples/` for the new shapes.
2. **Scripts / CI** — if you call `irag.py` directly, you can keep doing so, or switch to `mlm.py`. Both are the same core.
3. **AGENTS.md** — run `python install.py` again to refresh the AGENTS.md section with the new branding + markers. The old markers are migrated automatically.

## What continues to work automatically

- `INTERNAL_RAG/` storage folder — no rename, no migration.
- `irag.py` module — still present, still the canonical core.
- `.irag.yml` config — unchanged.
- `.index.sqlite3` — unchanged.
- Stored memories (Markdown) — unchanged.
- Old MCP server names in client configs — clients address servers by the key you give them; the server's `serverInfo.name` is now `mcp-light-memory`, but the key in your config is yours to name.

## What is deprecated

- The `irag` CLI command name (use `mlm`).
- The `internal-rag` MCP server display name (use `mcp-light-memory`).
- The `INTERNAL_RAG_START`/`INTERNAL_RAG_END` AGENTS.md markers (use `MCP_LIGHT_MEMORY_START`/`MCP_LIGHT_MEMORY_END`).
- The `[irag-router]` stderr log prefix (now `[mcp-light-memory-router]`).

Deprecated names are supported throughout the 1.7.x line. A future 2.0 may
remove them.

## Python package / module

The canonical Python module is still loaded from
`.agents/skills/internal-rag/irag.py` (the filename is intentionally kept for
compatibility). The new `mlm.py` shim in the same directory forwards all
arguments to `irag.py`. There is no `pip install` for the core — it remains
a single-file, zero-dependency drop-in.

If you previously imported internals from `irag.py` (e.g. in tests), those
imports keep working unchanged.

## Verification

After updating, run:

```bash
python .agents/skills/internal-rag/mlm.py --version
python .agents/skills/internal-rag/mlm.py status
python .agents/skills/internal-rag/mlm.py guard
```

You should see `MCP Light Memory v1.7.0` in the help text. `status` and
`guard` behave identically to before.

## Questions

- **Will my memories disappear?** No. Markdown is the source of truth and the folder name is unchanged.
- **Do I need to re-run `install.py`?** Recommended (to refresh AGENTS.md markers), but not required for functionality.
- **Can I keep using `irag.py` forever?** Throughout the 1.7.x line, yes. A future 2.0 may retire the alias.