# Recovery (v1.7.0)

If you see `RECOVERY REQUIRED`, do not make new edits.

1. Inspect:

```text
git status --short
git diff --stat
git diff
irag.py diff
```

2. Reconstruct the working state.
3. Save a checkpoint:

```text
irag.py checkpoint --reason "recovery" --phase "..." --completed "..." --in-progress "..." --blockers "..." --next "..."
```

4. Run `irag.py guard`.
5. Continue only after `GUARD OK`.

## Task stack (if interrupted)

If `irag.py tasks` shows remembered tasks:

```text
irag.py resume
```

`resume` restores the WORKING_STATE and reports whether the project code still matches (fingerprint fresh/stale).

## Diagnostics

```text
irag.py doctor
irag.py status
irag.py history
```

`doctor` reports missing pieces (dirs, checkpoint, python, embeddings). `history` shows recent checkpoints.