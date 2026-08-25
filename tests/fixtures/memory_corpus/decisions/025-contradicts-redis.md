---
id: mem-corp-025-contradicts-redis
type: decision
status: active
created: 2024-06-10
verified: 2024-06-10
confidence: medium
valid_from: 2024-06-10
scope:
  - cache
tags:
  - memcached
  - cache
  - session
sources:
  - docs/architecture/cache_v2.md
links: []
---

# Consider Memcached as alternative session store

## Knowledge

A proposal to switch session storage from Redis to Memcached for lower
latency on pure key-value access. This CONTRADICTS mem-corp-003-redis-cache
which decided on Redis. The team has not resolved the contradiction yet.

## Consequence

UNRESOLVED CONFLICT with mem-corp-003-redis-cache. Do not act until the team
picks one. This memory exists to test contradiction handling.