---
id: mem-corp-018-eslint-config
type: knowledge
status: active
created: 2024-05-01
verified: 2024-05-01
confidence: high
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

# ESLint flat config with prettier integration

## Knowledge

The frontend uses ESLint flat config (eslint.config.js) integrated with
Prettier. `eslint --fix` runs in pre-commit. The config extends
`eslint:recommended` and `plugin:react/recommended`.

## Consequence

New rules require a consensus PR. Prettier formatting is non-negotiable.