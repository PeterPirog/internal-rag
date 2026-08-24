# File map (v1.0.1)

## In the package (internal-rag repo)

- `install.py` — install/update.
- `uninstall.py` — full removal with backup.
- `privacy_check.py` — privacy & git audit.
- `self_test.py` — regression test.
- `pack.py` — offline packer (air-gapped support).
- `requirements-optional.txt` — optional embeddings dependencies.
- `README.md`, `docs/` — documentation.
- `VERSION`, `CHANGELOG.md` — versioning.

## In a target repo (after install)

- `AGENTS.md` — standing rules (INTERNAL_RAG section).
- `.irag.yml` — optional config (user-created or `config --init`).
- `.agents/skills/internal-rag/SKILL.md` — agent procedure.
- `.agents/skills/internal-rag/irag.py` — CLI (core, zero-dep).
- `.agents/skills/internal-rag/irag_embeddings.py` — optional embeddings plugin.
- `.agents/skills/internal-rag/irag_hooks.py` — optional git hooks installer.
- `.agents/skills/internal-rag/irag_index.py` — optional SQLite FTS5 index module.
- `INTERNAL_RAG/WORKING_STATE.md` — current checkpoint.
- `INTERNAL_RAG/INDEX.md` — durable memory index.
- `INTERNAL_RAG/.checkpoint.json` — last checkpoint metadata (schema-versioned).
- `INTERNAL_RAG/.tasks.json` — task stack (schema-versioned).
- `INTERNAL_RAG/.fpcache.json` — fingerprint cache.
- `INTERNAL_RAG/.index.sqlite3` — SQLite FTS5 index + usage store cache (rebuildable from Markdown; usage preserved across rebuilds by default).
- `INTERNAL_RAG/exports/` — JSON exports.
- `INTERNAL_RAG/usage-backups/` — timestamped backups created by `migrate-usage --apply --strip`.
- `INTERNAL_RAG/decisions/`, `knowledge/`, `gotchas/`, `failures/`, `hypotheses/` — durable memory.
- `INTERNAL_RAG/sessions/` — session summaries (user-created).
- `INTERNAL_RAG/sessions/.snapshots/` — auto WORKING_STATE snapshots (managed).
- `INTERNAL_RAG/archive/` — forgotten memories.
- `.opencode/tools/memory-*.ts` — OpenCode tools.
- `.opencode/plugins/internal-rag-resilience.ts` — auto-checkpoint + compact plugin.
- `.opencode/commands/memory*.md`, `checkpoint.md` — slash commands.

## Outside the working tree

- `.git/info/exclude` — local protection against accidental `git add`.
- `.git/internal-rag/manifest.json` — local install manifest.
- `.git/hooks/post-commit`, `post-checkout`, `pre-push` — optional hooks (if `irag_hooks.py install`).