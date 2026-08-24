# INTERNAL_RAG project memory

Ten katalog jest lokalną pamięcią operacyjną agenta.

Najważniejsze:
- `WORKING_STATE.md` — bieżący checkpoint,
- `INDEX.md` — indeks pamięci trwałej,
- `decisions/` — decyzje,
- `knowledge/` — wiedza i ograniczenia,
- `gotchas/` — pułapki,
- `failures/` — nieudane podejścia,
- `hypotheses/` — hipotezy,
- `sessions/` — opcjonalne streszczenia sesji.

Nie zapisuj tutaj haseł, tokenów, kluczy API, private keys ani danych produkcyjnych.

W domyślnej instalacji v0.4 cały katalog jest lokalnie ignorowany przez `.git/info/exclude`.
