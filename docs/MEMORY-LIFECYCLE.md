# Memory lifecycle (v1.0.1)

`WORKING_STATE.md` is short, frequently updated working memory (write-ahead checkpoint).

Store durable memory only for information useful in future sessions: decisions, constraints, root causes, gotchas, costly failed approaches, and hypotheses.

## What to store where

| Type | When to store | Default status |
|------|---------------|----------------|
| `decision` | A choice that affects future work (framework, library, architecture, pattern) | `active` |
| `knowledge` | A verified fact about the project (invariant, constraint, how something works) | `active` |
| `constraint` | A restriction that must be respected (API limits, compatibility, business rules) | `active` |
| `gotcha` | A non-obvious trap that cost time and could recur | `active` |
| `failure` | A failed approach that should not be repeated (with root cause) | `active` |
| `hypothesis` | An unverified idea or assumption — **not a fact** | `tentative` |
| `session` | A session summary (rarely needed; use checkpoints instead) | `active` |

## Statuses

- `active` — current, verified.
- `tentative` — hypothesis, unconfirmed (default for `hypothesis`).
- `superseded` — replaced by a newer one (`supersede --by`).
- `invalid` — wrong (`update --status invalid`).
- `archived` — forgotten (`forget` moves to `archive/`).

## Retrieval ranking

Memories are scored with **type-priority** so the most authoritative types surface first:
- `decision` (+0.8) > `knowledge` (+0.6) > `constraint` (+0.5) > `gotcha` (+0.4) > `failure` (+0.3) > `hypothesis` (+0.2) > `session` (+0.1)
- `active` status gets +1.0, `tentative` gets +0.6, `superseded` gets -4.0.

The `context` packet groups results:
- **Verified facts** (decisions, knowledge, constraints) — trust as established context.
- **Lessons & pitfalls** (gotchas, failures) — apply to avoid repeating mistakes.
- **Unverified hypotheses** — treat as tentative, verify before acting.

## CRUD

- `remember` — create.
- `show` / `timeline` — read.
- `update` — modify (status, tags, append).
- `supersede` — mark replaced.
- `forget` — archive (does not delete).
- `link` — cross-reference.

## Promote workflow

When a hypothesis is confirmed:
```bash
irag.py remember --type knowledge --title "Confirmed: X causes Y" --body "Verified by test Z."
irag.py supersede <hypothesis-ref> --by <new-knowledge-ref> --reason "confirmed in test Z"
```

When a hypothesis is disproven:
```bash
irag.py update <hypothesis-ref> --status invalid --append "Disproved by test Z."
```

## Rules

A hypothesis is not a fact and should remain `tentative` until verified.

If memory contradicts current code/tests: trust the code, mark the old memory `superseded`/`invalid`, record new evidence, and rebuild the index (`irag.py index`).

Never store: passwords, tokens, keys, production data, full logs, full chain-of-thought.