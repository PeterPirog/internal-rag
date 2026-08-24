---
id: mem-fix-019-nginx-timeout
type: gotcha
status: active
created: 2024-05-05
verified: 2024-05-05
scope:
  - infra
  - nginx
tags:
  - nginx
  - timeout
  - 504
sources:
  - nginx/sites-available/api.conf
links: []
---

# Nginx 504 Gateway Timeout on long API requests

## Knowledge

Nginx default proxy_read_timeout is 60s. Long-running report generation API calls exceed this. Need to increase to 300s for /reports endpoints.

## Consequence

Configure per-location timeout in nginx. Do not globally increase.