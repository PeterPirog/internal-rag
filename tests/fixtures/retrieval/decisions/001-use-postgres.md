---
id: mem-fix-001-use-postgres
type: decision
status: active
created: 2024-01-15
verified: 2024-01-15
scope:
  - database
tags:
  - postgres
  - database
  - infra
sources: []
links: []
last_accessed: 2026-08-24
---

# Use Postgres 16 for primary database

## Knowledge

Decided to use Postgres 16 for JSONB operators and pgvector extension support.

## Consequence

Need pgvector extension. All migrations must be Postgres-compatible.