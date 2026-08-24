# Codzienne użycie

## Start zadania

```text
irag.py context --task "opis zadania"
```

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
```

## Zapis trwałej wiedzy

```text
irag.py remember --type decision --title "..." --scope "..." --tags "..." --evidence "..." --body "..."
```

Typy: `decision`, `knowledge`, `constraint`, `gotcha`, `failure`, `hypothesis`, `session`.

## Koniec

```text
irag.py guard
```

Kończ po `GUARD OK`.

## Nie zapisuj

Haseł, tokenów, kluczy API, private keys, danych produkcyjnych, pełnych logów, pełnego chain-of-thought ani całej historii rozmowy.
