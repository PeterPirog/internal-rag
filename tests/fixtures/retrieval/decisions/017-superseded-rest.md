---
id: mem-fix-017-superseded-rest
type: decision
status: superseded
created: 2024-01-10
verified: 2024-01-10
superseded_by: mem-fix-002-auth-jwt
superseded_at: 2024-01-20
supersede_reason: JWT is more secure than basic auth
scope:
  - auth
tags:
  - rest
  - auth
  - basic
sources: []
links: []
---

# Use Basic Auth for API

## Knowledge

Initially decided to use HTTP Basic Auth for all API endpoints.

## Consequence

Superseded by JWT decision. Do not use.