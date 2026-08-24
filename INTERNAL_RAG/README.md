# INTERNAL_RAG project memory (v1.0.0)

Ten katalog jest lokalną pamięcią operacyjną agenta.

Najważniejsze:
- `WORKING_STATE.md` — bieżący checkpoint (write-ahead),
- `INDEX.md` — indeks pamięci trwałej,
- `.checkpoint.json` — metadane ostatniego checkpointu,
- `.tasks.json` — stos zadań (push/resume),
- `.fpcache.json` — cache fingerprint (auto),
- `exports/` — eksporty JSON (`irag.py export`),
- `decisions/` — decyzje,
- `knowledge/` — wiedza i ograniczenia,
- `gotchas/` — pułapki,
- `failures/` — nieudane podejścia,
- `hypotheses/` — hipotezy,
- `sessions/` — streszczenia sesji (user-created) + `.snapshots/` (auto),
- `archive/` — zapomniane pamięci (`irag.py forget`).

Nie zapisuj tutaj haseł, tokenów, kluczy API, private keys ani danych produkcyjnych.

W domyślnej instalacji v1.0 cały katalog jest lokalnie ignorowany przez `.git/info/exclude`.