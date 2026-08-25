---
id: mem-corp-032-multi-result-a
type: knowledge
status: active
created: 2024-08-01
verified: 2024-08-01
confidence: high
scope:
  - database
  - auth
tags:
  - database
  - auth
  - integration
sources:
  - src/api/users.py:40
links: []
---

# User API reads from the Postgres primary

## Knowledge

The user-facing API reads user profiles from the Postgres primary to avoid
replication lag for the authenticated user. Writes go to the primary;
read replicas serve only analytics endpoints.

## Consequence

This is one of two memories needed to answer "how does the user API talk to
the database and auth". Combine with mem-corp-002-auth-jwt.