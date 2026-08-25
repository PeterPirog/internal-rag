---
id: mem-corp-006-migration-rollback
type: gotcha
status: active
created: 2024-03-01
verified: 2024-03-01
confidence: high
scope:
  - database
  - migration
tags:
  - migration
  - rollback
  - alembic
sources:
  - migrations/versions/0042_add_index.py
links: []
---

# Alembic rollback drops dependent objects

## Knowledge

The Alembic migration `0042_add_index` cannot be rolled back with
`alembic downgrade -1` because the down_revision drops a dependent foreign
key without recreating it. The safe rollback is to restore from a snapshot
taken before the upgrade.

## Consequence

Always test `downgrade` on a staging copy. Take a pre-migration snapshot.