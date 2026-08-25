---
id: mem-corp-031-supersede-chain-c
type: decision
status: active
created: 2024-07-20
verified: 2024-07-20
confidence: high
valid_from: 2024-07-20
supersedes:
  - mem-corp-030-supersede-chain-b
scope:
  - search
tags:
  - search
  - postgres
  - fts
  - v3
sources:
  - docs/architecture/search_v3.md
links: []
---

# Use Postgres FTS for full-text search (v3, current)

## Knowledge

v3 uses Postgres `tsvector` + GIN index. No extra service. Good enough for
our corpus size and lets us keep the operational surface small.

## Consequence

This is the CURRENT decision. For history of the search stack, see
mem-corp-029-supersede-chain-a and mem-corp-030-supersede-chain-b.