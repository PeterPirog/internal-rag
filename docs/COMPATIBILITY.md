# Compatibility (v1.0.1)

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

- `irag.py mcp` — minimal JSON-RPC 2.0 stdio server (newline-delimited).
- Negotiates protocol versions `2025-11-25` / `2025-06-18` / `2025-03-26` /
  `2024-11-05` (returns the client's version when supported, else the latest).
- `irag_mcp_router.py` — multi-project router (registry allowlist,
  `write=false`, per-project subprocess isolation, `projects` tool).
- Verified against the official `mcp` Python SDK client (`mcp>=2,<3`) via
  `tests/test_mcp_sdk_compat.py` (skipped when the optional SDK is absent).

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