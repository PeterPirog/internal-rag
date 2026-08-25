# Compatibility (v1.7.0)

Verified: **2026-08-24**.

## Warp

Mechanisms used:
- `AGENTS.md` Project Rules,
- `.agents/skills/`.

Sources:
- https://docs.warp.dev/agent-platform/capabilities/rules
- https://docs.warp.dev/agent-platform/capabilities/skills

## OpenCode

Mechanisms used:
- `.agents/skills/`,
- `.opencode/tools/`,
- `.opencode/plugins/`,
- `.opencode/commands/`.

Sources:
- https://opencode.ai/docs/skills/
- https://opencode.ai/docs/custom-tools/
- https://opencode.ai/docs/plugins/

## MCP (Claude Code, Cursor, official `mcp` SDK)

- `irag.py mcp` — JSON-RPC 2.0 stdio server (newline-delimited).
- Dual-era: legacy (`2024-11-05`…`2025-11-25`) `initialize`/`tools/list`/`tools/call` + modern (`2026-07-28`) `server/discover` (no init), `_meta`, `resultType`, `structuredContent`, `outputSchema`.
- `irag_mcp_router.py` — multi-project router (registry allowlist, strict `write:false`, per-project subprocess isolation, `projects` tool, `structuredContent` passthrough).
- Verified against the official `mcp` Python SDK client (`mcp>=2,<3`) via `tests/test_mcp_sdk_compat.py` and `tests/test_mcp_modern.py` (raw 2026-07-28 stdio).

Source:
- https://modelcontextprotocol.io/

## Git

- Local-only mode uses `.git/info/exclude`.
- Optional hooks in `.git/hooks/` (post-commit, post-checkout, pre-push).

Source:
- https://git-scm.com/docs/gitignore

## Python

- Required: Python 3.8+.
- Optional: `sentence-transformers`, `numpy` (embeddings).
- Zero dependencies by default.

After a major Warp/OpenCode/MCP change, re-verify documentation and update the date. Run `self_test.py` after any change.