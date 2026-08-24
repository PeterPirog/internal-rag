# Warp (v1.0.1)

Warp recognizes `AGENTS.md` as Project Rules and skills in `.agents/skills/`.

After install, restart Warp in the repository.

Example:

```text
Continue the current task following AGENTS.md and INTERNAL_RAG.
```

You can also explicitly request: `Use skill internal-rag`.

Manual test on Windows:

```text
python .agents\skills\internal-rag\irag.py context --task "test"
```

OpenCode-specific hooks do not run in Warp, so checkpoint and guard remain important.

Warp does not support MCP tools; use the CLI directly or via the skill.