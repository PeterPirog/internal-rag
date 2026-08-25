---
id: mem-corp-019-nginx-timeout
type: gotcha
status: active
created: 2024-05-05
verified: 2024-05-05
confidence: high
scope:
  - infra
  - nginx
tags:
  - nginx
  - timeout
  - "504"
sources:
  - nginx/sites-available/api.conf
links: []
---

# nginx 504 Gateway Timeout under slow API calls

## Knowledge

nginx returns 504 when an upstream API call exceeds `proxy_read_timeout`
(default 60s). Long reports triggered this. The fix is to raise
`proxy_read_timeout 120s` for the `/reports` location only, and to move
long jobs to Celery.

## Consequence

Do not raise the global timeout. Move long work to a worker queue.