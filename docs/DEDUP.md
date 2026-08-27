# Duplicate detection algorithm (v1.7.0)

Cheap, deterministic duplicate detection for `remember`, `remember-batch`, and
`import`. No LLM, no third-party dependencies (pure stdlib: `hashlib`, `re`,
`unicodedata`).

## Signals (evaluated independently)

| Signal | Method | Action |
|--------|--------|--------|
| **Exact** | SHA-256 of the normalized canonical text | block by default |
| **Near** | 64-bit SimHash + Hamming distance ≤ 3 | block by default (warn) |
| **Title-similar** | Jaccard ≥ 0.7 on title tokens | block by default (warn) |
| **Conflict** | same type + scope overlap + ≥50% body token overlap | warn, recommend `supersede` |

All four can be bypassed with `--force`.

## Canonical text (`_canonical_memory_text`)

Includes: title, Knowledge body, Consequence, significant tags, significant scope.
Excludes: `created`/`updated`/`last_accessed` timestamps, `status`, id, links —
anything that changes without the memory itself changing.

Normalization: NFKD fold (diacritics stripped), casefold, whitespace collapse.
This makes equivalent text compare consistently across diacritic variants,
letter case, and whitespace differences; for example, `"use   database"` ≡
`"USE database"`, and `"a\n  b"` ≡ `"a b"`.

- **Exact fingerprint** = `sha256(canonical)`.
- **Near fingerprint** = 64-bit SimHash over tokenized canonical text:
  each token contributes a 64-bit MD5-based hash; per-bit weight sum decides
  the final bit. Similar texts land within a few Hamming bits.
  Threshold: Hamming distance ≤ 3 (configurable per call via
  `simhash_threshold`, default 3).

## Conflict ≠ duplicate

Opposing content ("Use Postgres" vs "Use MySQL") shares many tokens and may be
flagged as a **conflict** — that is the correct behavior. Conflicts are reported
under a separate `conflict` key (or warning text) and are **not** counted in
`duplicate.exact` / `duplicate.near` / `duplicate.title_similar`. The two result
classes never mix.

## Archived memories

Archived (or `invalid`/`superseded`) memories are never treated as *active*
duplicates: they do not block and do not set `recommended_action`. They are
still listed informationally in `near` with an `(archived ...)` marker so the
user can spot a forgotten memory being re-added.

## `--json` output shape

```json
{
  "status": "blocked | created | refused",
  "duplicate": {
    "exact": true,
    "near": ["INTERNAL_RAG/decisions/... (exact duplicate)"],
    "title_similar": ["INTERNAL_RAG/decisions/... (title: ..., 84%)"],
    "recommended_action": "update"
  }
}
```

`recommended_action` ∈ `update` (exact), `supersede` (near), `force` (nothing
stronger matched), or `null` (no signal). Conflict blocks report
`recommended_action: "supersede"` alongside the `conflict` list.

## Limitations

1. **SimHash is a heuristic**: very short memories (few tokens) have unstable
   fingerprints — distance ≤ 3 can false-positive on short, topic-overlapping
   notes. Short memories should be deduped by exact fingerprint + title Jaccard.
2. **Token-level only**: no word embeddings, no sentence semantics.
   Synonym paraphrases beyond 1-2 word changes can exceed the distance threshold.
3. **Order-insensitive but length-sensitive**: very long vs very short memories
   about the same topic may score either near or far depending on token overlap.
4. **Type-scoped**: only memories of the same `type` are compared, to avoid
   flagging a `decision` against an unrelated `knowledge` note.
5. **Not transitive**: A≈B and B≈C does not imply A≈C (standard SimHash caveat).
6. **Diacritics are folded** for comparison (NFKD), so letters with diacritics
   compare as their normalized base forms. This is intentional for mixed-language
   corpora.

## Tuning

- `simhash_threshold` (default 3) in `_check_duplicates(...)` — raise to 4–5 for
  more aggressive near-detection (more false positives), lower to 2 for stricter.
- Title Jaccard threshold 0.7 is hard-coded in `_find_duplicates`; change there.
- Conflict body-overlap threshold 0.5 in `_find_conflicts`.

## Tests

See `tests/test_dedup.py`:
- identical text, different title → near (not exact)
- identical title+body → exact, blocked
- opposing decision → **not** flagged as duplicate (separate conflict path)
- diacritics + whitespace differences → exact after normalization
- archived memory → informational only, does not block
- `--force` bypass; `--json` shape; import idempotency