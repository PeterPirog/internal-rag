---
id: mem-corp-003-redis-cache
type: decision
status: active
created: 2024-02-01
verified: 2024-02-01
confidence: high
valid_from: 2024-02-01
scope:
  - cache
  - infra
tags:
  - redis
  - cache
  - session
sources:
  - docs/architecture/cache.md
links: []
---

# Use Redis for session cache

## Knowledge

User sessions are stored in Redis with a TTL of 30 minutes and LRU eviction
per instance. The cache key is `session:<user_id>`. We chose Redis over
in-memory LRU so that sessions survive worker restarts and can be shared
across replicas.

## Consequence

A Redis outage logs everyone out. Sentinel provides failover.