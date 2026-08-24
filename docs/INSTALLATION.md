# Instalacja

## Wymagania

```text
python --version
git --version
```

Projekt docelowy musi być repozytorium Git.

## Tryb zalecany: local-only

Windows:

```powershell
python .\install.py "D:\projekty\moj-projekt"
```

Linux/macOS:

```bash
python3 install.py "/home/user/projekty/moj-projekt"
```

Po sukcesie zobaczysz `INSTALLATION COMPLETE`.

Instalator:
1. robi backup,
2. zachowuje istniejącą pamięć,
3. instaluje skill i CLI,
4. instaluje integrację OpenCode,
5. aktualizuje tylko oznaczoną sekcję `AGENTS.md`,
6. konfiguruje `.git/info/exclude`,
7. uruchamia `init` i `validate`.

## Tryb współdzielenia tools

Jeżeli chcesz commitować integracje do docelowego projektu:

```text
python install.py "D:\projekt" --share-tools
```

`INTERNAL_RAG/` nadal pozostaje lokalnie ignorowany.

## Aktualizacja

Uruchom nowy `install.py` na tym samym repo. Istniejący `WORKING_STATE.md` i katalogi pamięci są zachowywane.
