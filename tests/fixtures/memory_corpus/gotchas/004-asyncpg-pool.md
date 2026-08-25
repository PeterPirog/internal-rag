---
id: mem-corp-004-asyncpg-pool
type: gotcha
status: active
created: 2024-02-10
verified: 2024-02-10
confidence: high
scope:
  - database
  - async
tags:
  - asyncpg
  - pool
  - timeout
sources:
  - src/db/pool.py:42
links:
  - mem-corp-001-use-postgres
---

# asyncpg pool exhausts under burst load

## Knowledge

The asyncpg connection pool exhausts under burst traffic, surfacing as
`InterfaceError: too many connections`. The root cause is that pool acquire
timeout defaulted to 10s while queries took up to 30s under load. We set
`pool_size=20` and `command_timeout=30`.

## Consequence

Always size the pool to p95 query latency x expected concurrency. Monitor
`pool.get_size()` and `pool.get_idle_size()`.