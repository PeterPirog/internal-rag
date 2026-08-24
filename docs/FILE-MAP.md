# Mapa plików (v1.0.0)

## W paczce (repo internal-rag)

- `install.py` — instalacja/aktualizacja.
- `uninstall.py` — pełne usunięcie z backupem.
- `privacy_check.py` — audyt prywatności/Git.
- `self_test.py` — test regresyjny.
- `README.md`, `docs/` — dokumentacja.
- `VERSION`, `CHANGELOG.md` — wersjonowanie.

## W docelowym repo (po instalacji)

- `AGENTS.md` — stałe reguły (sekcja INTERNAL_RAG).
- `.irag.yml` — opcjonalna konfiguracja (user-created).
- `.agents/skills/internal-rag/SKILL.md` — procedura dla agenta.
- `.agents/skills/internal-rag/irag.py` — CLI (rdzeń, zero-dep).
- `.agents/skills/internal-rag/irag_embeddings.py` — opcjonalny plugin embeddings.
- `.agents/skills/internal-rag/irag_hooks.py` — opcjonalne git hooks.
- `INTERNAL_RAG/WORKING_STATE.md` — bieżący checkpoint.
- `INTERNAL_RAG/INDEX.md` — indeks pamięci trwałej.
- `INTERNAL_RAG/.checkpoint.json` — metadane ostatniego checkpointu.
- `INTERNAL_RAG/.tasks.json` — stos zadań.
- `INTERNAL_RAG/.fpcache.json` — cache fingerprint.
- `INTERNAL_RAG/exports/` — eksporty JSON.
- `INTERNAL_RAG/decisions/`, `knowledge/`, `gotchas/`, `failures/`, `hypotheses/` — pamięć trwała.
- `INTERNAL_RAG/sessions/` — streszczenia sesji (user-created).
- `INTERNAL_RAG/sessions/.snapshots/` — auto-snapshoty WORKING_STATE (zarządzane).
- `INTERNAL_RAG/archive/` — zapomniane pamięci.
- `.opencode/tools/memory-*.ts` — narzędzia OpenCode.
- `.opencode/plugins/internal-rag-resilience.ts` — plugin auto-checkpoint + compact.
- `.opencode/commands/memory*.md`, `checkpoint.md` — komendy slash.

## Poza working tree

- `.git/info/exclude` — lokalna ochrona przed przypadkowym `git add`.
- `.git/internal-rag/manifest.json` — lokalny manifest instalacji.
- `.git/hooks/post-commit`, `post-checkout`, `pre-push` — opcjonalne hooki (jeśli `irag_hooks.py install`).