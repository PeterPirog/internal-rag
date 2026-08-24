---
id: mem-fix-011-webpack-config
type: knowledge
status: active
created: 2024-04-01
verified: 2024-04-01
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

# Webpack config splits vendor and app bundles

## Knowledge

Webpack splits bundles: vendor.js for node_modules, app.js for application code. Source maps enabled in dev, disabled in production.

## Consequence

Build time increases with vendor splitting. Cache busting via content hash.