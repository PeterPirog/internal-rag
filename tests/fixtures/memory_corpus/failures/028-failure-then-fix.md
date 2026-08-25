---
id: mem-corp-028-failure-then-fix
type: failure
status: active
created: 2024-06-25
verified: 2024-06-25
confidence: high
scope:
  - worker
  - queue
tags:
  - celery
  - deadletter
  - failure
sources:
  - src/worker/deadletter.py:12
links:
  - mem-corp-010-celery-worker
---

# Celery tasks silently dropped before dead-letter queue

## Knowledge

Before the dead-letter queue was added, failed Celery tasks were retried
until max_retries and then dropped silently. We lost order confirmation
emails. The fix introduced a dead-letter queue that stores the task payload
and traceback for inspection.

## Consequence

Always monitor the dead-letter queue length. The failure->fix chain is:
this memory -> mem-corp-010-celery-worker (related config).