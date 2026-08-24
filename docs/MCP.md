# MCP server (v1.0.0)

INTERNAL_RAG dostarcza minimalny serwer MCP-over-stdio, kompatybilny z Claude Code, Cursor i innymi klientami MCP.

## Uruchomienie

```bash
python3 .agents/skills/internal-rag/irag.py mcp
```

## Protokół

Minimalny podzbiór JSON-RPC 2.0 po stdin/stdout:

- `initialize` — handshake, zwraca `protocolVersion`, `serverInfo`.
- `tools/list` — lista narzędzi.
- `tools/call` — wywołanie narzędzia z `name` i `arguments`.

## Narzędzia

| name | argumenty | opis |
|------|-----------|-----|
| `context` | `task`, `limit?` | Pakiet kontekstu (WORKING_STATE, kandydaci, tokeny, recovery) |
| `search` | `query`, `limit?` | BM25+MMR (embeddings jeśli dostępne) |
| `checkpoint` | `reason`, `phase?`, `completed?`, `in_progress?`, `blockers?`, `next?` | Zapis stanu |
| `guard` | — | Weryfikacja świeżości checkpointu |
| `remember` | `type`, `title`, `body`, `tags?`, `evidence?`, `scope?`, `consequence?` | Zapis pamięci trwałej |
| `status` | — | Przegląd pamięci i checkpointu |
| `tasks` | — | Stos zadań |
| `resume` | — | Wznów zadanie ze szczytu stosu |

## Konfiguracja w Claude Code

W `claude_desktop_config.json` (lub odpowiedniku):

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

Na Windows użyj `python` zamiast `python3` i ścieżek z `\\`.

## Uwagi

- Serwer nie wymaga zewnętrznych zależności (poza opcjonalnymi embeddings).
- Wszystkie wywołania operują na `INTERNAL_RAG/` w bieżącym katalogu roboczym (lub root git).
- Błędy zwracane są jako JSON-RPC error object (kod -32000).