# Mapa plików

## W paczce

- `install.py` — instalacja/aktualizacja.
- `uninstall.py` — pełne usunięcie z backupem.
- `privacy_check.py` — audyt prywatności/Git.
- `self_test.py` — test regresyjny.
- `README.md`, `docs/` — dokumentacja.

## W docelowym repo

- `AGENTS.md` — stałe reguły.
- `.agents/skills/internal-rag/SKILL.md` — procedura.
- `.agents/skills/internal-rag/irag.py` — CLI.
- `INTERNAL_RAG/WORKING_STATE.md` — checkpoint.
- `INTERNAL_RAG/INDEX.md` — indeks.
- katalogi `decisions`, `knowledge`, `gotchas`, `failures`, `hypotheses` — pamięć trwała.
- `.opencode/` — natywna integracja OpenCode.

## Poza working tree

- `.git/info/exclude` — lokalna ochrona przed przypadkowym `git add`.
- `.git/internal-rag/manifest.json` — lokalny manifest instalacji.
