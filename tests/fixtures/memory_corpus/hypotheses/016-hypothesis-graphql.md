---
id: mem-corp-016-hypothesis-graphql
type: hypothesis
status: tentative
created: 2024-04-25
verified: unverified
confidence: low
scope:
  - api
tags:
  - graphql
  - api
  - hypothesis
sources: []
links: []
---

# Hypothesis: GraphQL might reduce API calls

## Knowledge

We hypothesize that a GraphQL gateway could reduce the number of client
requests for the dashboard by collapsing 4 REST calls into one. No benchmark
yet.

## Consequence

Unverified. Do not act on this until a prototype is benchmarked.