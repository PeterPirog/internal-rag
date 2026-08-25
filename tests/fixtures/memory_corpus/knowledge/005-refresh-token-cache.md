---
id: mem-corp-005-refresh-token-cache
type: knowledge
status: active
created: 2024-02-15
verified: 2024-02-15
confidence: high
scope:
  - auth
  - cache
tags:
  - refresh_token_cache
  - auth
  - cache
sources:
  - src/auth/token.py:78
links:
  - mem-corp-002-auth-jwt
---

# refresh_token_cache function invalidates on password change

## Knowledge

The refresh_token_cache function in src/auth/token.py invalidates all refresh
tokens when a user changes their password. This prevents stale token usage
after credential rotation. The cache is keyed by user_id and stores a
`valid_after` timestamp.

## Consequence

Users must re-authenticate after password change. No silent token refresh.