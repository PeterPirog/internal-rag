# Configuration (`.irag.yml`, v1.0.1)

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
tokens:
  context_budget: 4000       # estimated token budget in context
  warn_ratio: 0.8            # warning threshold (in JSON output)
checkpoints:
  auto_archive_sessions: true   # archive WORKING_STATE snapshots in sessions/.snapshots/
  max_task_stack: 16            # max task stack depth
privacy:
  scan_on_checkpoint: false     # (reserved) run privacy scan on checkpoint
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

## RRF parameters

- `rrf_k` (default 60) — smoothing constant. Higher values flatten rank differences.
- `sparse_weight` (default 1.0) — weight for BM25 channel in fusion.
- `dense_weight` (default 1.0) — weight for dense channel in fusion.

## CLI override

`--embeddings on|off|auto` overrides the config for a single invocation.