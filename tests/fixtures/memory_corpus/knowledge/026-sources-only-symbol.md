---
id: mem-corp-026-sources-only-symbol
type: knowledge
status: active
created: 2024-06-15
verified: 2024-06-15
confidence: high
scope:
  - auth
  - security
tags:
  - auth
  - security
sources:
  - src/auth/session.py:140
  - src/auth/SessionManager.py:55
links:
  - mem-corp-002-auth-jwt
---

# Session manager rotates keys on a schedule

## Knowledge

The session key rotation is handled by the SessionManager. Keys are rotated
every 24 hours and the previous key remains valid for a grace window of 1
hour to avoid dropping in-flight requests.

## Consequence

Key material must be available to all replicas. The symbol name
SessionManager and the path src/auth/session.py are the primary retrieval
handles; the body does not repeat the exact symbol identifier.