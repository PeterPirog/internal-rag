---
id: mem-fix-018-eslint-config
type: knowledge
status: active
created: 2024-05-01
verified: 2024-05-01
scope:
  - frontend
  - lint
tags:
  - eslint
  - lint
  - frontend
sources:
  - frontend/.eslintrc.js
links: []
---

# ESLint config enforces no-console and no-unused-vars

## Knowledge

ESLint config prohibits console.log in production code and flags unused variables as errors. Prettier handles formatting.

## Consequence

CI fails on lint errors. Use proper logging utility instead of console.