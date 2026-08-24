# Recovery (v1.0.0)

Jeżeli widzisz `RECOVERY REQUIRED`, nie wykonuj nowych zmian.

1. Sprawdź:

```text
git status --short
git diff --stat
git diff
irag.py diff
```

2. Odtwórz stan pracy.
3. Zapisz checkpoint:

```text
irag.py checkpoint --reason "recovery" --phase "..." --completed "..." --in-progress "..." --blockers "..." --next "..."
```

4. Uruchom `irag.py guard`.
5. Kontynuuj dopiero po `GUARD OK`.

## Stos zadań (jeśli przerwano)

Jeżeli `irag.py tasks` pokazuje zapamiętane zadania:

```text
irag.py resume
```

`resume` przywraca WORKING_STATE i raportuje czy kod projektu nadal pasuje (fingerprint fresh/stale).

## Diagnostyka

```text
irag.py doctor
irag.py status
```

`doctor` zgłasza braki (katalogi, checkpoint, python, embeddings).