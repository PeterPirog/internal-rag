---
id: mem-fix-010-celery-worker
type: knowledge
status: active
created: 2024-03-20
verified: 2024-03-20
scope:
  - worker
  - queue
tags:
  - celery
  - worker
  - queue
sources:
  - src/worker/tasks.py:30
links: []
---

# Celery worker processes background jobs

## Knowledge

Celery workers process email sending, report generation, and data export. Queue routing uses task name prefixes. Dead letter queue handles failed tasks after 3 retries.

## Consequence

Need RabbitMQ or Redis as broker. Monitor queue depth.