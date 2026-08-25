---
id: mem-corp-024-future-feature-flag
type: decision
status: active
created: 2024-06-01
verified: 2024-06-01
confidence: medium
valid_from: 2024-06-01
scope:
  - feature_flags
tags:
  - feature_flags
  - launchdarkly
  - rollout
sources:
  - docs/architecture/feature_flags.md
links: []
---

# Feature flags managed by LaunchDarkly

## Knowledge

We use LaunchDarkly to gate new features. Flags are evaluated per request
via the server-side SDK. The default state for any new flag is OFF.

## Consequence

Removing a flag requires a deploy. Flag hygiene is enforced by the
`stale-flags` CI job.