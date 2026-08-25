---
id: mem-corp-027-derived-from-jwt
type: knowledge
status: active
created: 2024-06-20
verified: 2024-06-20
confidence: high
scope:
  - auth
  - monitoring
tags:
  - jwt
  - monitoring
  - observability
sources:
  - src/auth/metrics.py:8
derived_from:
  - mem-corp-002-auth-jwt
links:
  - mem-corp-002-auth-jwt
---

# JWT issuance is exported as a Prometheus metric

## Knowledge

As a derived consequence of the JWT decision, the AuthService now exports a
Prometheus counter `jwt_issued_total` labeled by audience. This lets us
detect token storms and abnormal refresh patterns.

## Consequence

Dashboards must alert on a sudden spike of `jwt_issued_total`.