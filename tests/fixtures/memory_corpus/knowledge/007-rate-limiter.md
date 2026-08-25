---
id: mem-corp-007-rate-limiter
type: knowledge
status: active
created: 2024-03-05
verified: 2024-03-05
confidence: high
scope:
  - api
  - security
tags:
  - rate_limiter
  - api
sources:
  - src/middleware/rate_limit.py:15
links: []
---

# Rate limiter uses token bucket per IP

## Knowledge

The RateLimiter class in src/middleware/rate_limit.py implements a token
bucket with a refill rate of 10 req/s and burst capacity of 20 per IP.
Excess requests get HTTP 429 with a Retry-After header.

## Consequence

Bursty legitimate clients may be throttled. Consider per-user buckets for
authenticated endpoints.