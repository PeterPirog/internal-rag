---
id: mem-corp-009-pytest-asyncio
type: gotcha
status: active
created: 2024-03-15
verified: 2024-03-15
confidence: high
scope:
  - test
  - async
tags:
  - pytest
  - asyncio
  - fixture
sources:
  - tests/conftest.py:20
links: []
---

# pytest-asyncio event loop fixture scope

## Knowledge

Under pytest-asyncio the `event_loop` fixture must be function-scoped; a
session-scoped loop leaks resources across async tests and causes
`RuntimeError: Event loop is closed`. The fix is to override the fixture
in conftest.py.

## Consequence

Never reuse an event loop across tests. Set `asyncio_mode = "auto"` with
function-scoped fixtures.