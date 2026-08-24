# Kompatybilność (v1.0.0)

Zweryfikowano: **2026-08-24**.

## Warp

Używane mechanizmy:
- `AGENTS.md` Project Rules,
- `.agents/skills/`.

Źródła:
- https://docs.warp.dev/agent-platform/capabilities/rules
- https://docs.warp.dev/agent-platform/capabilities/skills

## OpenCode

Używane mechanizmy:
- `.agents/skills/`,
- `.opencode/tools/`,
- `.opencode/plugins/`,
- `.opencode/commands/`.

Źródła:
- https://opencode.ai/docs/skills/
- https://opencode.ai/docs/custom-tools/
- https://opencode.ai/docs/plugins/

## MCP (Claude Code, Cursor)

- `irag.py mcp` — minimalny JSON-RPC stdio server.
- Kompatybilny ze specyfikacją MCP 2024-11-05 (podzbiór).

Źródło:
- https://modelcontextprotocol.io/

## Git

- Tryb local-only używa `.git/info/exclude`.
- Opcjonalne hooki w `.git/hooks/` (post-commit, post-checkout, pre-push).

Źródło:
- https://git-scm.com/docs/gitignore

## Python

- Wymagane: Python 3.8+.
- Opcjonalne: `sentence-transformers`, `numpy` (embeddings).
- Zero zależności domyślnie.

Przy większej zmianie Warp/OpenCode/MCP należy ponownie zweryfikować dokumentację i zaktualizować datę. Uruchom `self_test.py` po każdej zmianie.