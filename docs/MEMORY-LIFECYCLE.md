# Cykl życia pamięci (v1.0.0)

`WORKING_STATE.md` jest krótką, często aktualizowaną pamięcią roboczą (write-ahead checkpoint).

Pamięć trwałą zapisuj tylko dla informacji przydatnych w przyszłych sesjach: decyzji, ograniczeń, root cause, gotchas, kosztownych błędnych podejść i hipotez.

## Statusy

- `active` — aktualna, zweryfikowana.
- `tentative` — hipoteza, niepotwierdzona (domyślnie dla `hypothesis`).
- `superseded` — zastąpiona nowszą (`supersede --by`).
- `invalid` — błędna (`update --status invalid`).
- `archived` — zapomniana (`forget` przenosi do `archive/`).

## CRUD

- `remember` — tworzy.
- `show` / `timeline` — czyta.
- `update` — modyfikuje (status, tags, append).
- `supersede` — oznacza zastąpioną.
- `forget` — archiwizuje (nie usuwa).
- `link` — cross-reference.

## Zasady

Hipoteza nie jest faktem i powinna pozostać `tentative` do weryfikacji.

Jeżeli pamięć przeczy aktualnemu kodowi/testom: ufaj kodowi, oznacz starą pamięć jako `superseded`/`invalid`, zapisz nowe dowody i odśwież indeks (`irag.py index`).

Nie zapisuj: haseł, tokenów, kluczy, danych produkcyjnych, pełnych logów, pełnego chain-of-thought.