# Codzienne użycie (v1.0.0)

## Start zadania

```text
irag.py context --task "opis zadania"
```

Dla narzędzi: `irag.py context --task "..." --json`.

## Przed pierwszą zmianą

```text
irag.py checkpoint --reason "task-start"
```

## Po milestone

```text
irag.py checkpoint --reason "milestone" --phase "..." --completed "..." --next "..."
```

## Wyszukiwanie pamięci

```text
irag.py search --query "symbol subsystem problem" --limit 8
irag.py search --query "..." --json
```

BM25+MMR domyślnie; embeddings gdy dostępne i włączone w `.irag.yml`.

## Zapis trwałej wiedzy

```text
irag.py remember --type decision --title "..." --scope "..." --tags "..." --evidence "..." --body "..." --consequence "..."
```

Typy: `decision`, `knowledge`, `constraint`, `gotcha`, `failure`, `hypothesis`, `session`.

## Odczyt / aktualizacja pamięci

```text
irag.py show <path-or-id>
irag.py timeline --limit 20
irag.py update <ref> --status superseded --add-tags "new"
irag.py update <ref> --append "New evidence: ..."
irag.py supersede <ref> --by <new-ref> --reason "..."
irag.py forget <ref>
irag.py link --from <ref> --to <ref>
irag.py status
irag.py diff
```

## Stos zadań (przerwania)

```text
irag.py push --task "przerwana praca" --reason "user-priority"
irag.py tasks
irag.py resume
irag.py forget-task
```

## Kompresja (przed context compaction)

```text
irag.py compact
```

## Diagnostyka

```text
irag.py doctor
irag.py embeddings-info
irag.py config
irag.py validate
irag.py index
```

## Transfer pamięci

```text
irag.py export
irag.py import <file.json> --overwrite
```

## Koniec

```text
irag.py guard
```

Kończ po `GUARD OK`.

## Nie zapisuj

Haseł, tokenów, kluczy API, private keys, danych produkcyjnych, pełnych logów, pełnego chain-of-thought ani całej historii rozmowy.