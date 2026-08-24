---
id: mem-fix-003-redis-cache
type: decision
status: active
created: 2024-02-01
verified: 2024-02-01
scope:
  - cache
  - infra
tags:
  - redis
  - cache
sources: []
links: []
---

# Use Redis for session cache

## Knowledge

Redis handles session caching with 5-minute TTL. Cache invalidation on logout.

## Consequence

Redis must be highly available. Fallback to DB on cache miss.