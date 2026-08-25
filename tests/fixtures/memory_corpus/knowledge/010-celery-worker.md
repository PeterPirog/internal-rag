---
id: mem-corp-010-celery-worker
type: knowledge
status: active
created: 2024-03-20
verified: 2024-03-20
confidence: high
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

# Celery worker prefetch limits

## Knowledge

The Celery worker in src/worker/tasks.py uses `worker_prefetch_multiplier=1`
to avoid long-running tasks starving short ones. The broker is Redis with
two queues: `default` and `high_priority`.

## Consequence

Throughput drops for many tiny tasks. Tune the multiplier per workload.