---
id: mem-fix-005-refresh-token-cache
type: knowledge
status: active
created: 2024-02-15
verified: 2024-02-15
scope:
  - auth
  - cache
tags:
  - refresh_token_cache
  - auth
  - cache
sources:
  - src/auth/token.py:78
links: []
last_accessed: 2026-08-24
---

# refresh_token_cache function invalidates on password change

## Knowledge

The refresh_token_cache function in src/auth/token.py invalidates all refresh tokens when a user changes their password. This prevents stale token usage after credential rotation.

## Consequence

Users must re-authenticate after password change. No silent token refresh.