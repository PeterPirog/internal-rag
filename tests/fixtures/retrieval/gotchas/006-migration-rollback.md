---
id: mem-fix-006-migration-rollback
type: gotcha
status: active
created: 2024-03-01
verified: 2024-03-01
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

# Alembic migration rollback fails on partial indexes

## Knowledge

Alembic downgrade fails when a partial index was created with a WHERE clause. The downgrade script must drop the index before dropping the column.

## Consequence

Always test both upgrade and downgrade. Include index drops in downgrade scripts.