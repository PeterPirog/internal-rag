# Instalacja (v1.0.0)

## Wymagania

```text
python --version   # 3.8+
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
3. instaluje skill i CLI (`irag.py`, `irag_embeddings.py`, `irag_hooks.py`),
4. instaluje integrację OpenCode (tools, plugin, commands),
5. aktualizuje tylko oznaczoną sekcję `AGENTS.md`,
6. konfiguruje `.git/info/exclude` (w tym `.irag.yml`),
7. uruchamia `init` i `validate`.

## Tryb współdzielenia tools

Jeżeli chcesz commitować integracje do docelowego projektu:

```text
python install.py "D:\projekt" --share-tools
```

`INTERNAL_RAG/` nadal pozostaje lokalnie ignorowany.

## Opcjonalne: embeddings

```bash
pip install sentence-transformers numpy
```

W `.irag.yml`:

```yaml
retrieval:
  embeddings: auto
```

## Opcjonalne: git hooks

```bash
python3 .agents/skills/internal-rag/irag_hooks.py install
```

## Opcjonalne: MCP server

Zobacz `docs/MCP.md`.

## Aktualizacja

Uruchom nowy `install.py` na tym samym repo. Istniejący `WORKING_STATE.md` i katalogi pamięci są zachowywane.