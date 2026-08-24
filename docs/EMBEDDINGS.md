# Embeddings (optional, v1.3.0)

Since v1.1.0, INTERNAL_RAG uses **hybrid retrieval**: BM25 + optional dense embeddings combined via **Reciprocal Rank Fusion (RRF)**.

Since v1.3.0, corpus embeddings are **persistently cached** in SQLite (`.index.sqlite3`), so repeated searches do not re-encode documents.

## Persistent embedding cache

- Location: `INTERNAL_RAG/.index.sqlite3` (same DB as FTS5 index).
- Table: `embeddings(chunk_id, model_id, model_revision, dimension, precision, content_hash, vector, created_at)`.
- Format: float32, little-endian BLOB.
- Cache key: `(chunk_id, model_id, precision)` + `content_hash` match.
- Only changed chunks are re-encoded; unchanged chunks use cached vectors.
- Changing `last_accessed`/`access_count` does NOT invalidate embeddings.
- Changing model creates a new cache series (old cache preserved).

## How hybrid retrieval works

```text
query
  ├── BM25 sparse (always) ──→ sparse_ranked[]
  ├── Dense embeddings (if available)
  │     ├── Check persistent SQLite cache for corpus embeddings
  │     ├── Encode only missing/stale chunks
  │     ├── Store new embeddings in SQLite
  │     └── Compute cosine similarity ──→ dense_ranked[]
  └── RRF fusion ──→ fused[]
        ├── Policy boosts (status, type, recency)
        ├── MMR reranking (cosine diversity if dense, Jaccard fallback)
        └── Final top-k
```

RRF formula:
```
fused(doc) = sparse_weight / (rrf_k + sparse_rank)
           + dense_weight / (rrf_k + dense_rank)
```

This means a document found by **both** channels ranks higher than one found by only one — without summing incomparable raw scores.

## Install

```bash
pip install -r requirements-optional.txt
```

## Enable

In `.irag.yml`:

```yaml
retrieval:
  mode: hybrid      # sparse | dense | hybrid (default: hybrid)
  embeddings: auto  # auto | on | off (legacy, still works)
  rrf_k: 60
  sparse_weight: 1.0
  dense_weight: 1.0
```

- `hybrid` — BM25 + dense → RRF (default, best quality).
- `sparse` — BM25 only (zero-dependency).
- `dense` — dense only (graceful fallback to sparse if unavailable).

## `--explain`

```bash
irag.py search --query "auth" --json --explain
```

Returns per-result breakdown: `sparse_score`, `sparse_rank`, `dense_score`, `dense_rank`, `rrf_score`, `policy_boost`, `final_score`, `retrieval_mode`.

## Diagnostics

```bash
irag.py embeddings-info
irag.py embeddings-info --json
irag.py doctor
```

## When embeddings help

- Synonyms and paraphrases (BM25 misses these).
- Queries in a different language than the memory content.
- Longer, descriptive queries.
- Semantic similarity that exact token matching cannot capture.

## When BM25 suffices

- Exact token matches (file names, identifiers like `refresh_token_cache`).
- Small memory corpora.
- Environments where packages cannot be installed.

## Graceful degradation

If `sentence-transformers` is not installed, the model fails to load, or any error occurs:
- Dense channel returns `None`.
- RRF uses sparse-only results.
- No error is raised.
- `retrieval_mode` in `--explain` shows `sparse`.