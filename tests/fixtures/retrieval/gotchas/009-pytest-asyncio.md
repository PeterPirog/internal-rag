---
id: mem-fix-009-pytest-asyncio
type: gotcha
status: active
created: 2024-03-15
verified: 2024-03-15
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

# pytest-asyncio fixture scope must be function

## Knowledge

pytest-asyncio fixtures with scope=session cause event loop errors. Always use scope=function for async fixtures.

## Consequence

Session-scoped async resources need a sync wrapper.