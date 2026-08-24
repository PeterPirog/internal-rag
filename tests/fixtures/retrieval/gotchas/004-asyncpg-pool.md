---
id: mem-fix-004-asyncpg-pool
type: gotcha
status: active
created: 2024-02-10
verified: 2024-02-10
scope:
  - database
  - async
tags:
  - asyncpg
  - pool
  - timeout
sources:
  - src/db/pool.py:42
links: []
---

# asyncpg pool exhausts under load

## Knowledge

Pool exhausts without pool_size tuning. Default pool_size=10 is insufficient for >100 concurrent requests. Symptoms: connection timeout errors.

## Consequence

Set pool_size to at least 50 in production. Monitor pool utilization.