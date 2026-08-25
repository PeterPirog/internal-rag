---
id: mem-corp-001-use-postgres
type: decision
status: active
created: 2024-01-15
verified: 2024-01-15
confidence: high
valid_from: 2024-01-15
scope:
  - database
tags:
  - postgres
  - database
  - infra
sources:
  - docs/architecture/db.md
links: []
---

# Use Postgres 16 for primary database

## Knowledge

We decided to use Postgres 16 as the primary OLTP database across all
environments. The choice was driven by JSONB operator support and the
pgvector extension for optional embedding storage. The connection pool is
managed by asyncpg with a max size of 20 per worker.

## Consequence

All migrations must be Postgres-compatible. pgvector extension is required on
every environment. Failover is handled by Patroni.