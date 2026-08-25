# Troubleshooting (v1.7.0)

`RECOVERY REQUIRED` is not an error — see `RECOVERY.md`. `irag.py diff` shows what changed.

`GUARD STALE` means a change happened after the last checkpoint. Save a checkpoint and run guard again.

If OpenCode does not see tools: restart OpenCode, check `.opencode/tools/`, the worktree, and if needed use `irag.py` directly.

If Warp does not use the skill: restart Warp, check `AGENTS.md`, `.agents/skills/internal-rag/SKILL.md`, and explicitly request `internal-rag`.

If PowerShell blocks `.ps1`, run `python .\install.py "D:\project"` directly.

Embeddings unavailable: `irag.py doctor` and `irag.py embeddings-info` show the status. Install `pip install -r requirements-optional.txt` or use BM25 (default).

`irag.py mcp` not responding: the server reads stdin line by line (JSON-RPC). Ensure the client sends `initialize` before `tools/call`.

Git hooks not firing: check `.git/hooks/` and `irag_hooks.py status`. On Windows ensure git uses bash (Git for Windows).

Backup is in `~/.internal-rag-backups/` by default. If the home directory is not writable, the script falls back to a location next to the repo.

`irag.py doctor` reports issues — run `irag.py init` to create the directory structure.

CI workflow not pushed: the git token needs the `workflow` scope to push `.github/workflows/`.