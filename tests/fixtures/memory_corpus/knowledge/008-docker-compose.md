---
id: mem-corp-008-docker-compose
type: knowledge
status: active
created: 2024-03-10
verified: 2024-03-10
confidence: high
scope:
  - infra
  - docker
tags:
  - docker
  - docker-compose
  - dev
sources:
  - docker-compose.yml
links: []
---

# docker-compose dev environment

## Knowledge

The dev environment is defined in docker-compose.yml with services: api,
worker, postgres, redis. Hot reload is enabled via volume mounts. The
`make up` target boots everything; `make logs` tails the api.

## Consequence

Developers need Docker Desktop. WSL2 backend is recommended on Windows.