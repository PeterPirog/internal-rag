---
id: mem-corp-015-failed-nosql
type: failure
status: active
created: 2024-04-20
verified: 2024-04-20
confidence: high
scope:
  - database
tags:
  - mongodb
  - failure
  - nosql
sources:
  - docs/postmortems/2024-04-20-mongodb.md
links:
  - mem-corp-001-use-postgres
---

# Failed approach: MongoDB for transactional data

## Knowledge

We tried MongoDB for transactional workloads. It failed because multi-document
transactions are slow and the lack of JOINs forced denormalization that
diverged from the ORM. We reverted to Postgres within two weeks.

## Consequence

Never use MongoDB for transactional data in this project. Document stores are
acceptable only for audit logs.