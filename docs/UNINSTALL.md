# Deinstalacja

## Pełne oczyszczenie repo

Windows:

```powershell
python .\uninstall.py "D:\projekt"
```

Linux/macOS:

```bash
python3 uninstall.py "/projekt"
```

Program robi backup poza repo, usuwa `INTERNAL_RAG/`, skill, integrację OpenCode, własną sekcję z `AGENTS.md`, własny blok z `.git/info/exclude` i lokalny manifest.

Aby zachować pamięć: `--keep-memory`.

Aby pominąć backup: `--no-backup`.

Po deinstalacji uruchom `git status --short`. Jeżeli INTERNAL_RAG był kiedyś commitowany, usunięcie nie czyści historii.
