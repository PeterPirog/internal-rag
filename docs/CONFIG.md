# Configuration (`.irag.yml`, v1.0.1)

INTERNAL_RAG has sensible defaults — the `.irag.yml` file is optional.

## Full example

```yaml
retrieval:
  limit: 10                  # default number of search/context results
  mmr_lambda: 0.5            # 0=max diversity, 1=max relevance
  min_score: 0.5             # BM25 score threshold
  embeddings: auto           # auto | on | off
  embeddings_model: all-MiniLM-L6-v2   # sentence-transformers model
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
- `on` — require embeddings; fallback to BM25 on error.
- `off` — always BM25.

## CLI override

`--embeddings on|off|auto` overrides the config for a single invocation.