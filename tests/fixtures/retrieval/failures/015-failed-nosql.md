---
id: mem-fix-015-failed-nosql
type: failure
status: active
created: 2024-04-20
verified: 2024-04-20
scope:
  - database
tags:
  - mongodb
  - failure
  - nosql
sources: []
links: []
---

# Failed approach: MongoDB for transactional data

## Knowledge

Attempted to use MongoDB for transactional user data. Failed because MongoDB lacks multi-document ACID transactions in sharded clusters at scale.

## Consequence

Stay with Postgres for transactional data. MongoDB only for logs/analytics if needed.