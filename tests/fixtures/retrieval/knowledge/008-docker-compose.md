---
id: mem-fix-008-docker-compose
type: knowledge
status: active
created: 2024-03-10
verified: 2024-03-10
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

# Docker Compose setup for local development

## Knowledge

docker-compose.yml defines postgres, redis, and web services. The web service hot-reloads via volume mount. Postgres data persists in a named volume.

## Consequence

Requires Docker 20+. Port 5432 and 6379 must be free on the host.