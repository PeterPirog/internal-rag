# INTERNAL_RAG

Lokalna, trwała pamięć projektowa dla agentów programistycznych pracujących w terminalu (Warp, OpenCode, Claude Code, Cursor).

**Wersja:** 1.0.0  
**Zweryfikowano:** 2026-08-24  
**Integracje:** Warp, OpenCode, MCP (Claude Code / Cursor)
**Wymagania:** Python 3.8+, Git
**Opcjonalnie:** `sentence-transformers`, `numpy` (lepsze wyszukiwanie semantyczne)

INTERNAL_RAG przechowuje minimalny stan potrzebny do wznowienia złożonej pracy bez utrzymywania całej historii sesji w oknie kontekstowym modelu. Działa jak punkt kontrolny (checkpoint) + RAG dla agenta.

## Co nowego w 1.0.0

- **Retrieval BM25 + MMR** z opcjonalnymi embeddingami (zero-dep fallback).
- **Pełny CRUD pamięci**: `show`, `update`, `supersede`, `forget`, `link`, `status`, `diff`, `timeline`.
- **Stos zadań**: `push` / `tasks` / `resume` / `forget-task` dla przerwań.
- **Kompresja**: `compact` przed context compaction.
- **MCP server**: `irag.py mcp` (JSON-RPC stdio) dla Claude Code / Cursor.
- **Git hooks** (opcjonalne): auto-checkpoint po commicie, ostrzeżenie przed push.
- **Diagnostyka**: `doctor`, `embeddings-info`, `config`.
- **Transfer pamięci**: `export` / `import` (JSON).
- **Token budget**: estymacja tokenów w `context`.
- **`--json`** dla wszystkich komend strukturalnych.

## Szybki start

### Windows

```powershell
python .\install.py "D:\sciezka\do\projektu"
```

Następnie uruchom ponownie Warp/OpenCode i w projekcie:

```powershell
python .agents\skills\internal-rag\irag.py context --task "aktualne zadanie"
```

### Linux/macOS

```bash
python3 install.py "/sciezka/do/projektu"
```

Następnie:

```bash
python3 .agents/skills/internal-rag/irag.py context --task "aktualne zadanie"
```

## Model pracy

```text
context
  ↓
recovery, jeżeli wymagane
  ↓
checkpoint przed pierwszą zmianą
  ↓
implementacja
  ↓
checkpoint po istotnym etapie
  ↓
guard przed zakończeniem
```

Najważniejsze polecenia:

```text
irag.py context --task "..."
irag.py checkpoint --reason "..."
irag.py search --query "..." --limit 8
irag.py remember --type decision --title "..." --body "..."
irag.py show <ref>
irag.py update <ref> --status superseded
irag.py status
irag.py guard
irag.py validate
irag.py doctor
```

## Pamięć trwała (CRUD)

```text
remember --type decision --title "..." --body "..." --tags "a,b" --evidence "src/x.py:42"
show <path-or-id>
update <ref> --add-tags "new" --append "New evidence: ..."
supersede <ref> --by <new> --reason "..."
forget <ref>              # archiwizuje, nie usuwa
link --from <ref> --to <ref>
timeline --limit 20
status
```

Typy: `decision`, `knowledge`, `constraint`, `gotcha`, `failure`, `hypothesis`, `session`.

## Stos zadań (przerwania)

```text
irag.py push --task "przerwana praca" --reason "user-priority"
irag.py tasks
irag.py resume
irag.py forget-task
```

## MCP server (Claude Code / Cursor)

```bash
python3 .agents/skills/internal-rag/irag.py mcp
```

Minimalny JSON-RPC stdio: `context`, `search`, `checkpoint`, `guard`, `remember`, `status`, `tasks`, `resume`.

## Git hooks (opcjonalne, auto-checkpoint)

```bash
python3 .agents/skills/internal-rag/irag_hooks.py install
python3 .agents/skills/internal-rag/irag_hooks.py status
python3 .agents/skills/internal-rag/irag_hooks.py uninstall
```

Hooki nigdy nie blokują operacji git.

## Konfiguracja (`.irag.yml`, opcjonalna)

```yaml
retrieval:
  limit: 10
  mmr_lambda: 0.4
  min_score: 0.3
  embeddings: auto        # auto | on | off
  embeddings_model: all-MiniLM-L6-v2
tokens:
  context_budget: 5000
checkpoints:
  auto_archive_sessions: true
  max_task_stack: 24
```

`irag.py config` pokazuje efektywną konfigurację.

## Diagnostyka i transfer

```text
irag.py doctor
irag.py embeddings-info
irag.py export                  # -> INTERNAL_RAG/exports/
irag.py import <file.json> --overwrite
irag.py config
```

## Opcjonalne embeddings (lepszy retrieval)

```bash
pip install sentence-transformers numpy
```

Gdy pakiet jest dostępny i `.irag.yml` ma `embeddings: auto` (domyślnie), wyszukiwanie używa embeddingów z fallbackiem do BM25 gdy model niedostępny.

## Prywatność i Git

Domyślny tryb instalacji jest **local-only**. Instalator używa `.git/info/exclude`, a nie projektowego `.gitignore`, żeby lokalne pliki pamięci i integracji nie były przypadkowo dodawane do commitów.

Przed publikacją projektu:

```powershell
python .\privacy_check.py "D:\sciezka\do\projektu"
```

Oczekiwany wynik:

```text
RESULT: PASS
```

## Całkowite usunięcie z projektu

```powershell
python .\uninstall.py "D:\sciezka\do\projektu"
```

Deinstalator tworzy backup poza repozytorium, a następnie usuwa INTERNAL_RAG i jego integracje. Aby zachować samą pamięć, użyj `--keep-memory`.

## Dokumentacja

- [Instalacja](docs/INSTALLATION.md)
- [Codzienna praca](docs/DAILY-USAGE.md)
- [Architektura](docs/ARCHITECTURE.md)
- [Cykl życia pamięci](docs/MEMORY-LIFECYCLE.md)
- [Recovery](docs/RECOVERY.md)
- [Warp](docs/WARP.md)
- [OpenCode](docs/OPENCODE.md)
- [MCP](docs/MCP.md)
- [Konfiguracja](docs/CONFIG.md)
- [Embeddings](docs/EMBEDDINGS.md)
- [Prywatność i Git](docs/PRIVACY-AND-GIT.md)
- [Deinstalacja](docs/UNINSTALL.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Mapa plików](docs/FILE-MAP.md)
- [Kompatybilność](docs/COMPATIBILITY.md)
- [Publikacja na GitHub](docs/GITHUB-PUBLISHING.md)

## Struktura w docelowym projekcie

```text
projekt/
├── AGENTS.md
├── .irag.yml                    # opcjonalna konfiguracja
├── INTERNAL_RAG/
│   ├── WORKING_STATE.md
│   ├── INDEX.md
│   ├── .checkpoint.json
│   ├── .tasks.json
│   ├── .fpcache.json
│   ├── exports/
│   ├── decisions/
│   ├── knowledge/
│   ├── gotchas/
│   ├── failures/
│   ├── hypotheses/
│   ├── sessions/
│   │   └── .snapshots/
│   └── archive/
├── .agents/skills/internal-rag/
│   ├── SKILL.md
│   ├── irag.py
│   ├── irag_embeddings.py       # opcjonalny plugin
│   └── irag_hooks.py            # opcjonalne git hooks
└── .opencode/
    ├── tools/
    ├── commands/
    └── plugins/
```

## Źródło prawdy

1. bieżące polecenie użytkownika,
2. aktualny kod/testy/konfiguracja,
3. specyfikacje/ADR,
4. zweryfikowana pamięć,
5. notatki sesji,
6. hipotezy.

Pamięć może być nieaktualna. Kod ma pierwszeństwo.

## Licencja

MIT.