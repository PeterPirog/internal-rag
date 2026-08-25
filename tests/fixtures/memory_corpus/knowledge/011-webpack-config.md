---
id: mem-corp-011-webpack-config
type: knowledge
status: active
created: 2024-04-01
verified: 2024-04-01
confidence: high
scope:
  - frontend
  - build
tags:
  - webpack
  - frontend
  - build
sources:
  - frontend/webpack.config.js
links: []
---

# webpack production build splits vendor chunks

## Knowledge

The frontend/webpack.config.js splits vendor bundles (react, lodash) into a
separate chunk for long-term caching. Source maps are hidden in production.

## Consequence

Cache busting requires content hashes in filenames.