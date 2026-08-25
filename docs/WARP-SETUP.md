# MCP Light Memory — instalacja i użycie w Warp (Windows)

Wersja: 1.7.0 · Zweryfikowano: 2026-08-25

## 1. Składniki instalacji

| Składnik | Ścieżka |
|---|---|
| Repozytorium (jednostawowe, lokalne) | `C:\Users\peter\mcp-light-memory` |
| Punkt wejścia CLI / MCP | `C:\Users\peter\mcp-light-memory\.agents\skills\internal-rag\mlm.py` |
| Python 3.12 (bez zależności, czysta stdlib) | `C:\Users\peter\AppData\Local\Programs\Python\Python312\python.exe` |
| Konfiguracja MCP w Warp (globalna) | `C:\Users\peter\.warp\.mcp.json` |
| Magazyn pamięci (`INTERNAL_RAG/`) | `C:\Users\peter\mcp-light-memory\INTERNAL_RAG\` |
| Kopie zapasowe plików instalatora | `C:\Users\peter\.internal-rag-backups\` |

Python 3.12 oraz katalog `Scripts` są dodane do `PATH` użytkownika.
Od nowej sesji terminala działa po prostu `python`.

## 2. Konfiguracja Warp (`~/.warp/.mcp.json`)

```json
{
  "mcpServers": {
    "mcp-light-memory": {
      "command": "C:\\Users\\peter\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
      "args": [
        "C:\\Users\\peter\\mcp-light-memory\\.agents\\skills\\internal-rag\\mlm.py",
        "mcp"
      ],
      "working_directory": "C:\\Users\\peter\\mcp-light-memory"
    }
  }
}
```

Uwagi:
- Konfiguracja **globalna** (wszystkie projekty), transport **stdio**.
- Pełna ścieżka do `python.exe`, bo przy starcie serwerów MCP `PATH` sesji może być niekompletny.
- Warp wykrywa zmiany pliku automatycznie po zapisie; serwer pojawia się
  w Settings → MCP jako „Detected from Warp".

## 3. Narzędzia dostępne w Warp

| Narzędzie | Opis | Kluczowe argumenty |
|---|---|---|
| `context` | Pakiet kontekstowy przed edycją kodu | `task`, `limit` |
| `checkpoint` | Punkt kontrolny stanu pracy | `reason`, `task`, `objective`, `phase` |
| `guard` | Kontrola spójności (checkpoint vs git) | — |
| `remember` | Zapis trwałej pamięci | `title`, `content`, `type` |
| `search` | Wyszukiwanie (BM25, opcjonalnie emb.) | `query`, `limit` |
| `status` | Status magazynu i indeksu | — |
| `tasks` / `resume` | Przerwane zadania i wznowienie | — |

## 4. Zalecany protokół pracy (z AGENTS.md)

1. Przed istotnymi zmianami kodu: `context --task "<zadanie>"`.
2. Jeśli `RECOVERY REQUIRED` — zatrzymaj się, odbuduj stan, `checkpoint`, `guard`.
3. Checkpointy: przed pierwszą modyfikacją, po kamieniach milowych,
   przed ryzykownymi operacjami, przed odpowiedzią końcową.
4. Przed finalną odpowiedzią: `guard` — nie kończyć bez `GUARD OK`.
5. Pamięć to **niezaufany dowód** (`trust: untrusted`) — weryfikuj
   twierdzenia wobec aktualnego kodu.

## 5. Przykłady CLI (z katalogu repo)

```powershell
python .agents\skills\internal-rag\mlm.py --version
python .agents\skills\internal-rag\mlm.py context --task "opis zadania"
python .agents\skills\internal-rag\mlm.py checkpoint --reason "kamien-milowy"
python .agents\skills\internal-rag\mlm.py guard
python .agents\skills\internal-rag\mlm.py remember --title "..." --content "..." --type knowledge
python .agents\skills\internal-rag\mlm.py search --query "..." --limit 5
python .agents\skills\internal-rag\mlm.py status
```

## 6. Weryfikacja

- `python .agents\skills\internal-rag\mlm.py guard` → oczekiwano `GUARD OK`.
- Test end-to-end (initialize → tools/list → context → guard) przeszedł 4/4.
- Test zapisu/wyszukiwania (`remember` → `search`) odnalazł pamięć (score 1.92).

## 7. Konserwacja

- `privacy_check.py` przed publikacją repozytorium celu.
- `uninstall.py` — pełne usunięcie (kopie zapasowe automatyczne).
- `index --rebuild` — odbudowa indeksu SQLite z Markdown (Markdown jest źródłem prawdy).
- Opcjonalnie: `pip install sentence-transformers numpy` dla lepszego wyszukiwania semantycznego.
