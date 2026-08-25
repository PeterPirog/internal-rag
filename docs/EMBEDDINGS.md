# Embeddings (optional, v1.4.0)

Since v1.1.0, INTERNAL_RAG uses **hybrid retrieval**: BM25 + optional dense embeddings combined via **Reciprocal Rank Fusion (RRF)**.

Since v1.3.0, corpus embeddings are **persistently cached** in SQLite (`.index.sqlite3`), so repeated searches do not re-encode documents.

## Retrieval profiles (v1.7.0)

| Profile | Model | Query/passage encoding |
|---------|-------|------------------------|
| `english-fast` (**default**) | `all-MiniLM-L6-v2` | no prefix (model card: plain encode) |
| `multilingual` | `intfloat/multilingual-e5-small` | `query: ` / `passage: ` prefixes, as required by the E5 model card and Sentence Transformers |

- `retrieval.profile` selects the profile; `retrieval.embeddings_model` (explicit value) overrides it — an explicit model is encoded with **no prefix**.
- The in-memory embedding cache key **includes the model identity**, and the persistent cache is keyed by `(chunk_id, model_id, precision)` + content hash — switching profiles never reuses the other profile's vectors.
- `irag.py embeddings-info` reports the **active profile** and resolved model.
- `english-fast` remains the default for existing users; choose `multilingual` for Polish-English corpora (see Benchmark below).

## Sparse channel: code tokens vs natural language

- No external stemmer (pure stdlib `tokenize()`).
- Identifiers are preserved verbatim by the tokenizer, so exact matching works for
  `refresh_token_cache`, `AuthService.refresh()`, `src/auth/session.py` (underscores,
  dots, slashes and `()`-wrapped calls survive tokenization).
- A small, **opt-in** Polish stopword list exists (`retrieval.pl_stopwords`,
  default `true`): it removes Polish function words from the sparse channel only.
  It is benchmark-justified (see below) and conservative — identifiers, proper
  nouns and technical terms are never dropped.
- Hard-coded English query expansion remains as a compatibility layer and can be
  disabled with `retrieval.query_expansion: false`.

## Benchmark (v1.4.0, 22-memory fixture corpus)

Query set: 15 Polish, 15 English, 10 PL+code-identifier mixed; Recall@1/3/5 and
MRR per group; `tests/multilingual_benchmark.py` (run with
`pip install -r requirements-optional.txt` installed):

| pipeline / profile | PL R@1 / R@5 / MRR | EN R@1 / R@5 / MRR | MIXED R@1 / R@5 / MRR |
|---|---|---|---|
| sparse (BM25, default profile) | 62% / 81% / 0.690 | 81% / 100% / 0.870 | 60% / 70% / 0.625 |
| hybrid `english-fast` | 12% / 50% / 0.227 | 25% / 50% / 0.300 | 10% / 60% / 0.205 |
| hybrid `multilingual` | **19%** / 50% / **0.269** | 25% / **56%** / **0.319** | 10% / 60% / 0.205 |

PL-stopword experiment (sparse): PL group R@1 62%→69%, MRR 0.690→0.721 — kept
enabled by default (`pl_stopwords: true`) because it improves recall without
dropping exact-matching tokens; set `pl_stopwords: false` to revert.

Conclusions (do **not** treat multilingual as a universal default):
- `multilingual` improves the PL group over `english-fast` and does not regress
  EN/MIXED in hybrid mode → officially supported for PL/EN projects.
- On this small corpus, dense hybrid currently adds little over the sparse
  channel and costs significant latency; prefer `mode: sparse` (default) for
  latency-sensitive paths and re-run the benchmark on your own corpus before
  enabling hybrid.

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

## Section-aware chunking

Since v1.4.0, memories are chunked before embedding:
- Short memories (<threshold_chars) → 1 chunk.
- Long memories → split by Markdown `##` headings, with title/type/tags/scope prefix.
- Overlong sections → further split with configurable overlap.
- Chunk ID: `<memory_id>:<section-slug>:<ordinal>` (deterministic).

Only changed chunks are re-embedded (content hash per chunk). Changing one section does not invalidate other chunks' embeddings.

Config:
```yaml
retrieval:
  chunking:
    enabled: true
    threshold_chars: 2000
    target_chars: 1200
    overlap_chars: 120
```

## Graceful degradation

If `sentence-transformers` is not installed, the model fails to load, or any error occurs:
- Dense channel returns `None`.
- RRF uses sparse-only results.
- No error is raised.
- `retrieval_mode` in `--explain` shows `sparse`.