# Current Working State

updated: 2026-08-26T22:27:11+02:00
branch: fix/v1.8.1-hardening
base_commit: 56563ad

## Objective

v1.5.0: abstention gate + FTS5 prefilter + multi-project MCP router + CI/docs

## Current request

v1.8.1 hardening P2/P3 plugin fix

## Current phase

v1.8.1-hardening

## Completed

- ProjectWriteLock ownership token + dead-PID reclaim + multiprocess tests

## In progress

- docs update

## Blockers

- none

## Important active decisions

- None.

## Relevant files

- ` M` agents/skills/internal-rag/irag_ephemeral.py
- `??` tests/test_e2e_lifecycle.py

## Next actions

1. fix test_config_merge (add ephemeral+gc to known_sections) and finish test_e2e_lifecycle

## Checkpoint health

- CHECKPOINT CURRENT at save time.
- Run `irag.py guard` before final response.

## Recovery snapshot

- Checkpoint reason: lock fix committed 56563ad; e2e/config work in progress uncommitted
- Branch: fix/v1.8.1-hardening
- HEAD: 56563ad
- ` M` agents/skills/internal-rag/irag_ephemeral.py
- `??` tests/test_e2e_lifecycle.py

## Memory to retrieve if needed

- None.
