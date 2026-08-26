# Current Working State

updated: 2026-08-26T10:24:32+02:00
branch: feat/v1.8-mcp-compliance-ephemeral
base_commit: 1d0292e

## Objective

v1.5.0: abstention gate + FTS5 prefilter + multi-project MCP router + CI/docs

## Current request

MCP/OpenCode compatibility and ephemeral-memory lifecycle modernization

## Current phase

v1.6.0 complete

## Completed

- P0: MCP 2026-07-28 wire format + 21 conformance tests
- OpenCode 1 vs 2 installer + plugin split. P1: ephemeral observations, diagnostic distillation, GC + retention, session snapshot GC, atomic writes, OpenCode compaction integration. P2: value-aware forgetting. 340 tests pass, 0 deps, no retrieval regression.

## In progress

- docs update

## Blockers

- none

## Important active decisions

- None.

## Relevant files

- No project-code changes detected.

## Next actions

1. update docs: README, MCP.md, MEMORY-LIFECYCLE.md, CONFIG.md, ARCHITECTURE.md, ZERO-SHOT-SETUP-PROMPTS.md

## Checkpoint health

- CHECKPOINT CURRENT at save time.
- Run `irag.py guard` before final response.

## Recovery snapshot

- Checkpoint reason: completed v1.8.0: MCP 2026-07-28 compliance, OpenCode 1/2 split, ephemeral memory, distillation, GC, atomic writes
- Branch: feat/v1.8-mcp-compliance-ephemeral
- HEAD: 1d0292e
- No project-code changes detected.

## Memory to retrieve if needed

- None.
