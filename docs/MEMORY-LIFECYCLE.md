# Memory lifecycle (v1.0.1)

`WORKING_STATE.md` is short, frequently updated working memory (write-ahead checkpoint).

Store durable memory only for information useful in future sessions: decisions, constraints, root causes, gotchas, costly failed approaches, and hypotheses.

## Statuses

- `active` — current, verified.
- `tentative` — hypothesis, unconfirmed (default for `hypothesis`).
- `superseded` — replaced by a newer one (`supersede --by`).
- `invalid` — wrong (`update --status invalid`).
- `archived` — forgotten (`forget` moves to `archive/`).

## CRUD

- `remember` — create.
- `show` / `timeline` — read.
- `update` — modify (status, tags, append).
- `supersede` — mark replaced.
- `forget` — archive (does not delete).
- `link` — cross-reference.

## Rules

A hypothesis is not a fact and should remain `tentative` until verified.

If memory contradicts current code/tests: trust the code, mark the old memory `superseded`/`invalid`, record new evidence, and rebuild the index (`irag.py index`).

Never store: passwords, tokens, keys, production data, full logs, full chain-of-thought.