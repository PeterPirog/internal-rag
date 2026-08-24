# INTERNAL_RAG project memory (v1.0.1)

This directory is the agent's local operational memory.

Key entries:
- `WORKING_STATE.md` — current checkpoint (write-ahead),
- `INDEX.md` — durable memory index,
- `.checkpoint.json` — last checkpoint metadata,
- `.tasks.json` — task stack (push/resume),
- `.fpcache.json` — fingerprint cache (auto),
- `exports/` — JSON exports (`irag.py export`),
- `decisions/` — decisions,
- `knowledge/` — knowledge and constraints,
- `gotchas/` — gotchas,
- `failures/` — failed approaches,
- `hypotheses/` — hypotheses,
- `sessions/` — session summaries (user-created) + `.snapshots/` (auto),
- `archive/` — forgotten memories (`irag.py forget`).

Never store passwords, tokens, API keys, private keys, or production data here.

In the default v1.0 install, the whole directory is locally ignored via `.git/info/exclude`.