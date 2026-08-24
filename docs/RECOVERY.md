# Recovery

Jeżeli widzisz `RECOVERY REQUIRED`, nie wykonuj nowych zmian.

1. Sprawdź:

```text
git status --short
git diff --stat
git diff
```

2. Odtwórz stan pracy.
3. Zapisz checkpoint:

```text
irag.py checkpoint --reason "recovery" --phase "..." --completed "..." --in-progress "..." --blockers "..." --next "..."
```

4. Uruchom `irag.py guard`.
5. Kontynuuj dopiero po `GUARD OK`.
