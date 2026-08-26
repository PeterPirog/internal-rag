# Configuration (`.irag.yml`, v1.6.0)

INTERNAL_RAG has sensible defaults — the `.irag.yml` file is optional.

## Full example

```yaml
retrieval:
  limit: 10                  # default number of search/context results
  mmr_lambda: 0.5            # 0=max diversity, 1=max relevance
  min_score: 0.5             # score threshold
  embeddings: auto           # auto | on | off (legacy, still works)
  embeddings_model: all-MiniLM-L6-v2   # sentence-transformers model
  bm25_k1: 1.5               # BM25 term frequency saturation (1.2-2.0 typical)
  bm25_b: 0.75               # BM25 length normalization (0.0-1.0)
  mode: hybrid               # sparse | dense | hybrid
  rrf_k: 60                  # RRF smoothing constant (higher = flatter)
  sparse_weight: 1.0         # RRF weight for BM25 channel
  dense_weight: 1.0          # RRF weight for dense channel
   candidate_multiplier: 4    # over-fetch factor for candidate pool
   profile: english-fast      # english-fast | multilingual (v1.4.0, default: english-fast)
   embeddings_model: null     # explicit model path/name overrides the profile (no prefix)
   query_expansion: true      # English synonym expansion (compat layer; set false to disable)
   pl_stopwords: true         # small PL function-word list on the sparse channel (benchmark-justified)
    chunking:                  # section-aware chunking (v1.8.0)
      enabled: true
      threshold_chars: 2000    # memories shorter than this become a single chunk
      target_chars: 1200       # target chunk size for overlong sections
      overlap_chars: 120       # overlap between split pieces
    abstention:                # relevance/admission gate (v1.8.0)
      enabled: true
      require_sparse_match: true   # sparse results must evidence a token match
      min_dense_score: null        # per-profile calibrated threshold (null = accept dense as-is)
    fts_prefilter:             # FTS5 candidate prefilter (v1.8.0)
      enabled: true
      min_corpus_size: 50      # skip prefilter overhead on tiny corpora
tokens:
  context_budget: 4000       # estimated token budget in context
  warn_ratio: 0.8            # warning threshold (in JSON output)
checkpoints:
  auto_archive_sessions: true   # archive WORKING_STATE snapshots in sessions/.snapshots/
  max_task_stack: 16            # max task stack depth
privacy:
  scan_on_checkpoint: false     # (reserved) run privacy scan on checkpoint
usage:
  stale_days: 30               # doctor: "stale" = last_accessed older than this many days
```

## Where config is loaded from

1. `<project>/.irag.yml` (if it exists)
2. Built-in defaults (in `irag.py`)

`irag.py config` prints the effective configuration. `irag.py config --json` — as JSON. `irag.py config --init` — writes a template `.irag.yml`.

## Environment variables

- `IRAG_EMBED_MODEL` — overrides `retrieval.embeddings_model`.

## Embeddings modes

- `auto` (default) — use embeddings if `sentence-transformers` is available; otherwise BM25.
- `on` — prefer embeddings, fallback to BM25 on error.
- `off` — always BM25.

## Retrieval modes (new in 1.1.0)

- `hybrid` (default) — BM25 + dense → RRF fusion → MMR. Best of both worlds.
- `sparse` — BM25 only. Zero-dependency.
- `dense` — attempt dense only; graceful fallback to sparse if unavailable.

`retrieval.embeddings` (old config) remains compatible:
- `embeddings: off` → behaves as `mode: sparse`.
- `embeddings: on|auto` → behaves as `mode: hybrid` (dense attempted, fallback to sparse).

## Abstention gate (new in 1.5.0)

The relevance/admission gate runs on RAW retrieval evidence, before any
policy boost. It decides whether a candidate is allowed into the ranked set —
policy can only rank admitted candidates, never rescue an irrelevant one.

- `enabled` — master switch for the gate.
- `require_sparse_match` — in `sparse`/`hybrid` modes a candidate must
  evidence at least one sparse-matched token actually present in the document.
- `min_dense_score` — optional calibrated threshold for dense evidence
  (`0.0-1.0`); `null` accepts dense evidence as-is (conservative default).

When every candidate is rejected, `search --json --meta` reports
`"abstained": true` with a human-readable `reason` (see "Abstention JSON" in
`docs/CLI.md`).

## FTS5 candidate prefilter (new in 1.5.0)

Optional accelerator for the sparse channel. When enabled and the corpus is
large enough, FTS5 provides a top-n candidate set which is unioned with the
Python BM25 top-k before scoring. It narrows the scoring pool — it never
changes the ranking and never drops a hit the full scan would return.

- `enabled` — master switch.
- `min_corpus_size` — prefilter is skipped below this corpus size
  (avoiding overhead on tiny corpora).

Automatic fallback to the full Python scan happens when: the index is
missing or stale (any memory file newer than the index), FTS5 is unavailable,
or the query yields no FTS5 matches.

## RRF parameters

- `rrf_k` (default 60) — smoothing constant. Higher values flatten rank differences.
- `sparse_weight` (default 1.0) — weight for BM25 channel in fusion.
- `dense_weight` (default 1.0) — weight for dense channel in fusion.

## CLI override

`--embeddings on|off|auto` overrides the config for a single invocation.


## Ephemeral observations (v1.8.0)

```yaml
ephemeral:
  ttl_seconds: 1800          # 30 minutes default
  max_records: 200
  max_bytes: 2097152         # 2 MB total
  max_record_bytes: 65536    # 64 KB per observation
```

## GC / retention (v1.8.0)

```yaml
gc:
  stale_days: 90             # reduce retrieval priority after 90d disuse
  gc_candidate_days: 180     # archive candidate after 180d disuse
  archive_after_days: 365    # archive after 1 year
  grace_days: 30             # physical delete 30d after archiving
```

## Session snapshot GC (v1.8.0)

```yaml
snapshots:
  max_age_days: 30
  max_count: 20
  max_bytes: 0               # 0 = unlimited
```
