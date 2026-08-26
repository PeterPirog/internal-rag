# Current Working State

updated: 2026-08-26T08:50:13+02:00
branch: main
base_commit: 579b0dd

## Objective

v1.5.0: abstention gate + FTS5 prefilter + multi-project MCP router + CI/docs

## Current request

MCP/OpenCode compatibility and ephemeral-memory lifecycle modernization

## Current phase

v1.6.0 complete

## Completed

- A: memory_quality_benchmark (37 cases, R@1 63.6%, R@5 96.9%, leak 0%)
- B: MCP 2026-07-28 dual-era
- C: schema+annotations+structuredContent
- D: search at+explain
- E: strict write bool
- F: sources in chunk prefix
- G: adaptive mode (opt-in, benchmark-gated)
- H: bounded link-aware context
- I: consolidate --prepare
- J: router latency bench (64ms overhead, no pool)
- K: MCP client docs+examples
- L: 16 modern MCP tests
- 187 tests OK
- self_test PASS
- all benchmarks green
- ADR-010..014

## In progress

- none

## Blockers

- none

## Important active decisions

- None.

## Relevant files

- ` M` agents/skills/internal-rag/irag.py
- ` M` agents/skills/internal-rag/irag_index.py
- ` M` agents/skills/internal-rag/irag_mcp_router.py
- ` M` github/workflows/ci.yml
- ` M` CHANGELOG.md
- ` M` README.md
- ` M` VERSION
- ` M` docs/ADR.md
- ` M` docs/COMPATIBILITY.md
- ` M` docs/MCP.md
- ` M` examples/jetbrains.example.json
- ` D` examples/opencode.example.json
- ` M` examples/warp.example.json
- ` M` install.py
- ` M` pack.py
- ` M` tests/test_mcp_router.py
- ` M` uninstall.py
- `??` agents/skills/internal-rag/irag_mcp_protocol.py
- `??` examples/opencode-legacy.example.json
- `??` examples/opencode-v2.example.jsonc
- `??` tests/fixtures/memory_corpus/archive/023-archived-legacy-migration.md
- `??` tests/fixtures/memory_corpus/decisions/001-use-postgres.md
- `??` tests/fixtures/memory_corpus/decisions/002-auth-jwt.md
- `??` tests/fixtures/memory_corpus/decisions/003-redis-cache.md
- `??` tests/fixtures/memory_corpus/decisions/013-polski-baza-danych.md
- `??` tests/fixtures/memory_corpus/decisions/017-superseded-rest.md
- `??` tests/fixtures/memory_corpus/decisions/024-future-feature-flag.md
- `??` tests/fixtures/memory_corpus/decisions/025-contradicts-redis.md
- `??` tests/fixtures/memory_corpus/decisions/029-supersede-chain-a.md
- `??` tests/fixtures/memory_corpus/decisions/030-supersede-chain-b.md
- `??` tests/fixtures/memory_corpus/decisions/031-supersede-chain-c.md
- `??` tests/fixtures/memory_corpus/decisions/033-future-not-yet-valid.md
- `??` tests/fixtures/memory_corpus/failures/015-failed-nosql.md
- `??` tests/fixtures/memory_corpus/failures/028-failure-then-fix.md
- `??` tests/fixtures/memory_corpus/gotchas/004-asyncpg-pool.md
- `??` tests/fixtures/memory_corpus/gotchas/006-migration-rollback.md
- `??` tests/fixtures/memory_corpus/gotchas/009-pytest-asyncio.md
- `??` tests/fixtures/memory_corpus/gotchas/014-polski-cache.md
- `??` tests/fixtures/memory_corpus/gotchas/019-nginx-timeout.md
- `??` tests/fixtures/memory_corpus/hypotheses/016-hypothesis-graphql.md
- `??` tests/fixtures/memory_corpus/knowledge/005-refresh-token-cache.md
- `??` tests/fixtures/memory_corpus/knowledge/007-rate-limiter.md
- `??` tests/fixtures/memory_corpus/knowledge/008-docker-compose.md
- `??` tests/fixtures/memory_corpus/knowledge/010-celery-worker.md
- `??` tests/fixtures/memory_corpus/knowledge/011-webpack-config.md
- `??` tests/fixtures/memory_corpus/knowledge/012-polski-logowanie.md
- `??` tests/fixtures/memory_corpus/knowledge/018-eslint-config.md
- `??` tests/fixtures/memory_corpus/knowledge/020-polski-walidacja.md
- `??` tests/fixtures/memory_corpus/knowledge/021-distractor-meeting.md
- `??` tests/fixtures/memory_corpus/knowledge/022-distractor-coffee.md
- ... 6 more

## Next actions

1. commit + push + tag v1.6.0

## Checkpoint health

- RECOVERY REQUIRED: project code differs from the last checkpoint.
- Inspect `git status` and `git diff`, reconstruct state, checkpoint it, then run guard.

## Recovery snapshot

- Checkpoint reason: v1.6.0 complete: CEL A-L all done
- Branch: main
- HEAD: 579b0dd
- ` M` agents/skills/internal-rag/irag.py
- ` M` agents/skills/internal-rag/irag_index.py
- ` M` agents/skills/internal-rag/irag_mcp_router.py
- ` M` github/workflows/ci.yml
- ` M` CHANGELOG.md
- ` M` README.md
- ` M` VERSION
- ` M` docs/ADR.md
- ` M` docs/COMPATIBILITY.md
- ` M` docs/MCP.md
- ` M` examples/jetbrains.example.json
- ` D` examples/opencode.example.json
- ` M` examples/warp.example.json
- ` M` install.py
- ` M` pack.py
- ` M` tests/test_mcp_router.py
- ` M` uninstall.py
- `??` agents/skills/internal-rag/irag_mcp_protocol.py
- `??` examples/opencode-legacy.example.json
- `??` examples/opencode-v2.example.jsonc
- `??` tests/fixtures/memory_corpus/archive/023-archived-legacy-migration.md
- `??` tests/fixtures/memory_corpus/decisions/001-use-postgres.md
- `??` tests/fixtures/memory_corpus/decisions/002-auth-jwt.md
- `??` tests/fixtures/memory_corpus/decisions/003-redis-cache.md
- `??` tests/fixtures/memory_corpus/decisions/013-polski-baza-danych.md
- `??` tests/fixtures/memory_corpus/decisions/017-superseded-rest.md
- `??` tests/fixtures/memory_corpus/decisions/024-future-feature-flag.md
- `??` tests/fixtures/memory_corpus/decisions/025-contradicts-redis.md
- `??` tests/fixtures/memory_corpus/decisions/029-supersede-chain-a.md
- `??` tests/fixtures/memory_corpus/decisions/030-supersede-chain-b.md
- `??` tests/fixtures/memory_corpus/decisions/031-supersede-chain-c.md
- `??` tests/fixtures/memory_corpus/decisions/033-future-not-yet-valid.md
- `??` tests/fixtures/memory_corpus/failures/015-failed-nosql.md
- `??` tests/fixtures/memory_corpus/failures/028-failure-then-fix.md
- `??` tests/fixtures/memory_corpus/gotchas/004-asyncpg-pool.md
- `??` tests/fixtures/memory_corpus/gotchas/006-migration-rollback.md
- `??` tests/fixtures/memory_corpus/gotchas/009-pytest-asyncio.md
- `??` tests/fixtures/memory_corpus/gotchas/014-polski-cache.md
- `??` tests/fixtures/memory_corpus/gotchas/019-nginx-timeout.md
- `??` tests/fixtures/memory_corpus/hypotheses/016-hypothesis-graphql.md
- `??` tests/fixtures/memory_corpus/knowledge/005-refresh-token-cache.md
- `??` tests/fixtures/memory_corpus/knowledge/007-rate-limiter.md
- `??` tests/fixtures/memory_corpus/knowledge/008-docker-compose.md
- `??` tests/fixtures/memory_corpus/knowledge/010-celery-worker.md
- `??` tests/fixtures/memory_corpus/knowledge/011-webpack-config.md
- `??` tests/fixtures/memory_corpus/knowledge/012-polski-logowanie.md
- `??` tests/fixtures/memory_corpus/knowledge/018-eslint-config.md
- `??` tests/fixtures/memory_corpus/knowledge/020-polski-walidacja.md
- `??` tests/fixtures/memory_corpus/knowledge/021-distractor-meeting.md
- `??` tests/fixtures/memory_corpus/knowledge/022-distractor-coffee.md
- ... 6 more

## Memory to retrieve if needed

- None.
