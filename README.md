# INTERNAL_RAG

Lokalna, trwała pamięć projektowa dla agentów programistycznych pracujących w terminalu.

**Wersja:** 0.4.0  
**Zweryfikowano:** 2026-08-22  
**Integracje:** Warp, OpenCode  
**Wymagania:** Python 3, Git

INTERNAL_RAG przechowuje minimalny stan potrzebny do wznowienia złożonej pracy bez utrzymywania całej historii sesji w oknie kontekstowym modelu.

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
irag.py search --query "..."
irag.py remember ...
irag.py guard
irag.py validate
```

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
├── INTERNAL_RAG/
│   ├── WORKING_STATE.md
│   ├── INDEX.md
│   ├── decisions/
│   ├── knowledge/
│   ├── gotchas/
│   ├── failures/
│   ├── hypotheses/
│   ├── sessions/
│   └── archive/
├── .agents/skills/internal-rag/
│   ├── SKILL.md
│   └── irag.py
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
