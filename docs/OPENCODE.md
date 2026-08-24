# OpenCode

OpenCode używa:
- `.agents/skills/internal-rag/SKILL.md`,
- `.opencode/tools/`,
- `.opencode/plugins/internal-rag-resilience.ts`,
- `.opencode/commands/`.

Tools: `memory-context`, `memory-search`, `memory-checkpoint`, `memory-guard`.

Commands: `/memory`, `/checkpoint`, `/memory-check`, `/memory-guard`.

Plugin próbuje checkpointować po modyfikacji plików, przy session error, przy idle i przed compaction.

Jeżeli native tool zawiedzie, agent może zawsze wywołać `irag.py` przez terminal.
