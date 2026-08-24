# Embeddings (optional, v1.0.1)

By default INTERNAL_RAG uses **BM25 + MMR** (pure Python, zero dependencies). For better semantic retrieval you can add sentence-transformers.

## Install

```bash
pip install -r requirements-optional.txt
```

First use will download the model (~80–400 MB depending on the model) to the user cache.

## Enable

In `.irag.yml`:

```yaml
retrieval:
  embeddings: auto      # auto (default) | on | off
  embeddings_model: all-MiniLM-L6-v2
```

- `auto` — embeddings if the package is available, otherwise BM25.
- `on` — prefer embeddings, fallback to BM25 on error.
- `off` — always BM25.

CLI override: `irag.py search --query "..." --embeddings on`.

## How it works

1. `irag.py` lazy-imports `irag_embeddings.py` (which imports `sentence_transformers`).
2. Embeddings are cached in-process (SHA-256 key).
3. Embedding scores are combined with status heuristics (active/tentative/superseded).
4. On any failure — automatic fallback to BM25+MMR.

## Diagnostics

```bash
irag.py embeddings-info
irag.py embeddings-info --json
irag.py doctor
```

## Models

Default: `all-MiniLM-L6-v2` (fast, ~80 MB). Alternatives:

```yaml
retrieval:
  embeddings_model: paraphrase-multilingual-MiniLM-L12-v2   # better for non-English
```

or `IRAG_EMBED_MODEL=...` env var.

## When embeddings help

- Synonyms and paraphrases (BM25 misses these).
- Queries in a different language than the memory content.
- Longer, descriptive queries.

## When BM25 suffices

- Exact token matches (file names, identifiers).
- Small memory corpora.
- Environments where packages cannot be installed.