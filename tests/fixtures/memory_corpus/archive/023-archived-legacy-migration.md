---
id: mem-corp-023-archived-legacy-migration
type: decision
status: archived
created: 2023-09-01
verified: 2023-09-01
confidence: low
valid_from: 2023-09-01
valid_to: 2024-01-15
scope:
  - database
  - migration
tags:
  - legacy
  - migration
  - archived
sources:
  - migrations/legacy/0001_init.py
links: []
---

# Legacy initial migration used raw SQL

## Knowledge

The very first migration used raw SQL files instead of Alembic. This was
replaced by the Alembic-managed migrations in 2024. Kept only for history.

## Consequence

Archived. Do not use. This memory must NOT surface in active search.