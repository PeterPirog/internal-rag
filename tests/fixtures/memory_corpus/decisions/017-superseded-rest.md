---
id: mem-corp-017-superseded-rest
type: decision
status: superseded
created: 2024-01-10
verified: 2024-01-10
confidence: high
valid_from: 2024-01-10
valid_to: 2024-01-20
superseded_by: mem-corp-002-auth-jwt
superseded_at: 2024-01-20
supersede_reason: JWT is more secure than basic auth
scope:
  - auth
tags:
  - rest
  - auth
  - basic
sources:
  - docs/architecture/auth_v1.md
links: []
---

# Use HTTP Basic Auth for API

## Knowledge

We initially used HTTP Basic Auth over TLS for the API. Basic auth is simple
but couples credentials to every request and offers no token revocation.

## Consequence

Superseded by mem-corp-002-auth-jwt on 2024-01-20. Kept for history.