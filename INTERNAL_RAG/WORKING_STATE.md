# Current Working State

updated: 2026-08-25T09:03:19+02:00
branch: main
base_commit: efb9ac8

## Objective

v1.5.0: abstention gate + FTS5 prefilter + multi-project MCP router + CI/docs

## Current request

v1.5.0: FTS5 prefilter done (C); E router, G CI, H docs remaining

## Current phase

v1.5.0 complete

## Completed

- A1-A5,B,C,D,E,G,H all done
- 168 tests OK (mcp+no-mcp)
- self_test PASS
- venv sim CI green

## In progress

- none

## Blockers

- none

## Important active decisions

- None.

## Relevant files

- ` M` agents/skills/internal-rag/irag.py
- ` D` github/workflows/self-test.yml
- ` M` CHANGELOG.md
- ` M` README.md
- ` M` VERSION
- ` M` docs/CLI.md
- ` M` docs/COMPATIBILITY.md
- ` M` docs/CONFIG.md
- ` M` docs/FILE-MAP.md
- ` M` docs/MCP.md
- ` M` install.py
- ` M` pack.py
- ` M` tests/test_lifecycle.py
- ` M` uninstall.py
- `??` agents/skills/internal-rag/irag_mcp_router.py
- `??` github/workflows/ci.yml
- `??` docs/ADR.md
- `??` docs/MCP-MULTI-PROJECT.md
- `??` examples/jetbrains.example.json
- `??` examples/opencode.example.json
- `??` examples/projects.example.json
- `??` examples/warp.example.json
- `??` tests/test_admission_gate.py
- `??` tests/test_config_merge.py
- `??` tests/test_fingerprint_cache.py
- `??` tests/test_fts_prefilter.py
- `??` tests/test_mcp_router.py
- `??` tests/test_mcp_sdk_compat.py
- `??` tests/test_mcp_server.py

## Next actions

1. commit + tag (await user)
2. optional F(HTTP/SSE)

## Checkpoint health

- CHECKPOINT CURRENT at save time.
- Run `irag.py guard` before final response.

## Recovery snapshot

- Checkpoint reason: H complete: docs+VERSION+CHANGELOG 1.5.0
- Branch: main
- HEAD: efb9ac8
- ` M` agents/skills/internal-rag/irag.py
- ` D` github/workflows/self-test.yml
- ` M` CHANGELOG.md
- ` M` README.md
- ` M` VERSION
- ` M` docs/CLI.md
- ` M` docs/COMPATIBILITY.md
- ` M` docs/CONFIG.md
- ` M` docs/FILE-MAP.md
- ` M` docs/MCP.md
- ` M` install.py
- ` M` pack.py
- ` M` tests/test_lifecycle.py
- ` M` uninstall.py
- `??` agents/skills/internal-rag/irag_mcp_router.py
- `??` github/workflows/ci.yml
- `??` docs/ADR.md
- `??` docs/MCP-MULTI-PROJECT.md
- `??` examples/jetbrains.example.json
- `??` examples/opencode.example.json
- `??` examples/projects.example.json
- `??` examples/warp.example.json
- `??` tests/test_admission_gate.py
- `??` tests/test_config_merge.py
- `??` tests/test_fingerprint_cache.py
- `??` tests/test_fts_prefilter.py
- `??` tests/test_mcp_router.py
- `??` tests/test_mcp_sdk_compat.py
- `??` tests/test_mcp_server.py

## Memory to retrieve if needed

- None.
