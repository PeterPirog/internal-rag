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

## MCP (Claude Code, Cursor)

- `irag.py mcp` — minimal JSON-RPC stdio server.
- Compatible with MCP spec 2024-11-05 (subset).

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