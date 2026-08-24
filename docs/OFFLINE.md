# Offline / air-gapped usage (v1.0.2)

INTERNAL_RAG is designed to work **fully offline** — the core (BM25+MMR) has zero external dependencies. For air-gapped environments with self-hosted models, you can also pre-package optional embeddings.

## Zero-dependency mode (default)

The core CLI (`irag.py`) requires only Python 3.8+ and Git. No pip install needed. BM25+MMR retrieval, CRUD, MCP server, git hooks — all work offline.

```bash
python install.py "/path/to/project"
python .agents/skills/internal-rag/irag.py context --task "task"
```

## Full offline pack (with embeddings)

On a machine **with** internet, choose the retrieval profile (default `english-fast`;
use `multilingual` for Polish-English projects):

```bash
python pack.py --with-embeddings --profile english-fast
# or, for a PL/EN project:
python pack.py --with-embeddings --profile multilingual
# or pin an explicit model:
python pack.py --with-embeddings --model all-MiniLM-L6-v2
```

This creates `internal-rag-offline-<version>.zip` containing:
- The full INTERNAL_RAG package.
- `wheels/` — `sentence-transformers` + `numpy` as `.whl` files.
- `models/` — the embeddings model pre-downloaded and saved.
- `OFFLINE-README.txt` — step-by-step instructions.

On the **air-gapped** machine:

```bash
# 1. Unzip
unzip internal-rag-offline-*.zip -d internal-rag-offline
cd internal-rag-offline

# 2. Install wheels (optional, for embeddings)
pip install --no-index --find-links wheels/ -r requirements-optional.txt

# 3. Install INTERNAL_RAG into your project
python install.py "/path/to/project"

# 4. Point to the pre-downloaded model
export IRAG_EMBED_MODEL="/path/to/internal-rag-offline/models/all-MiniLM-L6-v2"

# 5. Verify
python .agents/skills/internal-rag/irag.py doctor
python .agents/skills/internal-rag/irag.py embeddings-info
```

On Windows:
```powershell
set IRAG_EMBED_MODEL=C:\path\to\internal-rag-offline\models\all-MiniLM-L6-v2
```

## Self-hosted models

INTERNAL_RAG works with any local model compatible with sentence-transformers. Point `IRAG_EMBED_MODEL` (or `.irag.yml` `retrieval.embeddings_model`) to a local path:

```yaml
retrieval:
  embeddings: on
  embeddings_model: /opt/models/my-local-model
```

If the model path is invalid or the package is missing, INTERNAL_RAG silently falls back to BM25 — no crash.

## Offline verification checklist

```bash
irag.py doctor              # health check
irag.py embeddings-info     # engine status
irag.py context --task "test"   # end-to-end test
irag.py search --query "test"   # retrieval test
```

Expected without embeddings: `engine: bm25-fallback`.
Expected with embeddings: `engine: sentence-transformers`.

## What does NOT work offline

- Downloading embeddings models from HuggingFace (must be pre-packaged).
- `pip install sentence-transformers` from PyPI (must use `--find-links wheels/`).
- GitHub Actions CI (obviously).

Everything else — CRUD, search, checkpoint, guard, MCP, hooks, export/import, doctor — works fully offline.