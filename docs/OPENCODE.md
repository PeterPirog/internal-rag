# OpenCode (v1.0.0)

OpenCode używa:
- `.agents/skills/internal-rag/SKILL.md`,
- `.opencode/tools/`,
- `.opencode/plugins/internal-rag-resilience.ts`,
- `.opencode/commands/`.

## Tools (native)

- `memory-context` — start/resume zadania (context packet + recovery).
- `memory-search` — wyszukiwanie BM25+MMR/embeddings.
- `memory-checkpoint` — zapis stanu.
- `memory-guard` — weryfikacja świeżości.
- `memory-remember` — zapis pamięci trwałej.
- `memory-status` — przegląd pamięci.

Wszystkie narzędzia wspierają `--json` (gdzie ma to sens).

## Commands (slash)

- `/memory <task>` — start zadania.
- `/checkpoint` — zapis stanu + guard.
- `/memory-check` — index + status + validate + guard.
- `/memory-guard` — tylko guard.

## Plugin (resilience)

`internal-rag-resilience.ts`:
- `tool.execute.after` — auto-checkpoint po `edit`/`write`/`apply_patch`.
- `session.error` — checkpoint + sugestia inspekcji.
- `session.idle` — checkpoint.
- `experimental.session.compacting` — `compact` + checkpoint + wstrzykuje WORKING_STATE do kontekstu.

Jeżeli native tool zawiedzie, agent może zawsze wywołać `irag.py` przez terminal.