---
id: mem-corp-030-supersede-chain-b
type: decision
status: superseded
created: 2024-07-10
verified: 2024-07-10
confidence: high
valid_from: 2024-07-10
valid_to: 2024-07-20
superseded_by: mem-corp-031-supersede-chain-c
superseded_at: 2024-07-20
supersede_reason: v3 uses Postgres FTS, fewer services
supersedes:
  - mem-corp-029-supersede-chain-a
scope:
  - search
tags:
  - search
  - typesense
  - v2
sources: []
links: []
---

# Use Typesense for full-text search (v2)

## Knowledge

v2 used Typesense. Better latency than ES but still an extra service.
Superseded by v3.

## Consequence

Superseded by mem-corp-031-supersede-chain-c on 2024-07-20. Kept for history.