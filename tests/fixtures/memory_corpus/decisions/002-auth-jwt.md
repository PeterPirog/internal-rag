---
id: mem-corp-002-auth-jwt
type: decision
status: active
created: 2024-01-20
verified: 2024-01-20
confidence: high
valid_from: 2024-01-20
scope:
  - auth
tags:
  - jwt
  - auth
  - security
sources:
  - docs/architecture/auth.md
links:
  - mem-corp-005-refresh-token-cache
supersedes:
  - mem-corp-017-superseded-rest
---

# Authentication uses JWT tokens

## Knowledge

We use short-lived JWT access tokens (15 min) and refresh tokens (7 d) issued
by AuthService.refresh(). The refresh_token_cache function invalidates all
refresh tokens on a password change. Tokens are signed with RS256.

## Consequence

Clients must refresh access tokens before expiry. Key rotation requires
coordinated deploy of the public key.