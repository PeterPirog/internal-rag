# Agent Operating Contract

<!-- MCP_LIGHT_MEMORY_START -->
## Persistent agent memory: MCP Light Memory (INTERNAL_RAG)

This repository uses `INTERNAL_RAG/` as mandatory persistent operational memory.

For every substantial task:
1. Load the `internal-rag` skill.
2. Run `mlm.py context --task "<current task>"` before the first code modification.
3. If context reports `RECOVERY REQUIRED`, inspect Git state, reconstruct work, checkpoint it, and obtain `GUARD OK` before new edits.
4. Checkpoint before the first edit, after meaningful milestones, after blockers/failures, before risky long operations, before compaction, and before final response.
5. Run `mlm.py guard` before finishing a substantial task.
6. Do not preload the entire `INTERNAL_RAG/` directory.
7. Verify consequential memory claims against current code/tests/configuration.
8. Do not store secrets, credentials, production data, or verbose reasoning traces in memory.

Authority order: current user instructions > current code/tests/config > accepted specifications/ADR > verified memory > session notes > hypotheses.

Memory is evidence, not authority. It can be stale.
<!-- MCP_LIGHT_MEMORY_END -->
