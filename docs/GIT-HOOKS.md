# Git hooks (optional, v1.0.1)

INTERNAL_RAG can install local Git hooks that call `irag.py` automatically. Hooks are local-only (never tracked) and **never block git operations**.

## Install / uninstall / status

```bash
python3 .agents/skills/internal-rag/irag_hooks.py install
python3 .agents/skills/internal-rag/irag_hooks.py status
python3 .agents/skills/internal-rag/irag_hooks.py uninstall
```

## Hooks

| hook | behavior |
|------|----------|
| `post-commit` | Runs `irag.py checkpoint --reason git-post-commit`. Records a checkpoint after each commit. |
| `post-checkout` | Removes `.fpcache.json` so the next `context`/`guard` recomputes the fingerprint and detects stale state. |
| `pre-push` | Runs `irag.py guard` and prints a warning if stale. Never blocks the push. |

## Safety

- All hooks `exit 0` regardless of `irag.py` outcome.
- If `irag.py` is missing, hooks no-op.
- Hooks are appended to existing hooks (managed block marked with `# INTERNAL_RAG managed hook`).
- `uninstall` removes only the managed block, preserving user content.

## Windows note

Git for Windows uses bash to run hooks. The hooks are POSIX shell scripts and work under Git Bash. If you use a different shell, adapt the hook scripts in `.git/hooks/`.

## When to use hooks

- You want automatic checkpoints after every commit.
- You want a stale-checkpoint warning before pushing.
- You switch branches frequently and want recovery detection.

## When NOT to use hooks

- Shared repos where you do not want local automation.
- CI environments (hooks are local-only and not pushed).