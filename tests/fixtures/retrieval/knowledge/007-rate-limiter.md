---
id: mem-fix-007-rate-limiter
type: knowledge
status: active
created: 2024-03-05
verified: 2024-03-05
scope:
  - api
  - security
tags:
  - rate_limiter
  - api
sources:
  - src/middleware/rate_limit.py:15
links: []
last_accessed: 2026-08-24
---

# Rate limiter uses sliding window algorithm

## Knowledge

The rate limiter middleware uses a sliding window with Redis sorted sets. Each API endpoint has a configurable limit per user per minute.

## Consequence

Redis latency affects rate limit checks. Consider local fallback for critical paths.