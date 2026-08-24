---
id: mem-fix-002-auth-jwt
type: decision
status: active
created: 2024-01-20
verified: 2024-01-20
scope:
  - auth
tags:
  - jwt
  - auth
  - security
sources: []
links: []
last_accessed: 2026-08-24
---

# Authentication uses JWT tokens

## Knowledge

Auth middleware validates JWT tokens with RS256 signing. Token lifetime is 15 minutes.

## Consequence

Need JWKS endpoint. Refresh token flow required.