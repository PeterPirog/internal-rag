#!/usr/bin/env python3
"""Optional embeddings retrieval for INTERNAL_RAG.

This module is loaded lazily by irag.py only when the user has opted in
via `.irag.yml` (`retrieval.embeddings: on`) and the optional dependency
`sentence-transformers` is importable. It must never be imported at module
import time of irag.py; if anything fails, irag.py falls back to BM25.

Required optional packages:
    pip install sentence-transformers numpy

Function contract:
    embeddings_search(query, candidates, limit, cfg, root) -> list | None
        Returns a list of (score, Path, frontmatter_dict, snippet, matched_tokens)
        or None if embeddings cannot be computed (model load failure, etc.).
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import os
import re

_MODEL_CACHE: Dict[str, Any] = {}
_EMBED_CACHE: Dict[str, Any] = {}

DEFAULT_MODEL = os.environ.get("IRAG_EMBED_MODEL", "all-MiniLM-L6-v2")

RETRIEVAL_PROFILES = {
    "english-fast": {
        "model": "all-MiniLM-L6-v2",
        "query_prefix": "",
        "passage_prefix": "",
    },
    "multilingual": {
        "model": "intfloat/multilingual-e5-small",
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
    },
}


def _resolve_model(cfg: Dict[str, Any]) -> Tuple[str, str, str]:
    """Resolve model name, query prefix, and passage prefix from config.
    Returns (model_name, query_prefix, passage_prefix)."""
    profile = str(cfg.get("retrieval", {}).get("profile", "english-fast")).lower()
    explicit_model = cfg.get("retrieval", {}).get("embeddings_model")
    # Explicit model overrides profile
    if explicit_model and str(explicit_model).lower() not in ("null", "none", ""):
        return (str(explicit_model), "", "")
    prof = RETRIEVAL_PROFILES.get(profile, RETRIEVAL_PROFILES["english-fast"])
    return (prof["model"], prof["query_prefix"], prof["passage_prefix"])


def _load_model(model_name: str):
    if model_name in _MODEL_CACHE:
        return _MODEL_CACHE[model_name]
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        return None
    # Support local model paths (for offline / air-gapped use)
    model_path = Path(model_name)
    if model_path.is_dir():
        try:
            model = SentenceTransformer(str(model_path))
        except Exception:
            return None
    else:
        try:
            model = SentenceTransformer(model_name)
        except Exception:
            try:
                model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception:
                return None
    _MODEL_CACHE[model_name] = model
    return model


def _embed(model, texts: List[str], model_key: str = "default"):
    import numpy as np
    # Cache key includes the model identity + text so different profiles
    # (e.g. english-fast vs multilingual) never share cached vectors.
    key = hashlib.sha256((model_key + "\x1f" + "\n".join(texts)).encode("utf-8")).hexdigest()
    if key in _EMBED_CACHE:
        return _EMBED_CACHE[key]
    emb = model.encode(texts, convert_to_numpy=True, show_progress_bar=False, normalize_embeddings=True)
    _EMBED_CACHE[key] = emb
    return emb


def _tokenize_light(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9_./:@+-]{2,}", text.lower())


def embeddings_search(query: str,
                      candidates: List[Tuple[Path, str, Dict[str, Any]]],
                      limit: int,
                      cfg: Dict[str, Any],
                      root: Path) -> Optional[List[Tuple[float, Path, Dict[str, Any], str, List[str]]]]:
    """Legacy interface — returns full results with policy boosts applied.
    Kept for backward compatibility. New code should call dense_search_raw."""
    raw = dense_search_raw(query, candidates, cfg, root)
    if raw is None:
        return None
    TYPE_PRIORITY = {
        "decision": 0.8, "knowledge": 0.6, "constraint": 0.5,
        "gotcha": 0.4, "failure": 0.3, "hypothesis": 0.2, "session": 0.1,
    }

    def _recency_boost(fm):
        import datetime as _dt
        date_str = str(fm.get("updated") or fm.get("created") or "")
        if not date_str:
            return 0.0
        try:
            mem_date = _dt.date.fromisoformat(date_str[:10])
        except Exception:
            return 0.0
        age_days = (_dt.date.today() - mem_date).days
        if age_days < 0:
            age_days = 0
        if age_days <= 7:
            return 0.03
        if age_days <= 30:
            return 0.01
        return 0.0

    scored: List[Tuple[float, int]] = []
    for cosine_sim, i in raw:
        fm = candidates[i][2]
        status = str(fm.get("status", "active")).lower()
        score = float(cosine_sim)
        if status == "active":
            score += 0.1
        elif status == "tentative":
            score += 0.06
        elif status == "superseded":
            score -= 0.2
        elif status in ("invalid", "archived"):
            score -= 10.0
        mtype = str(fm.get("type", "")).lower()
        score += TYPE_PRIORITY.get(mtype, 0.0)
        score += _recency_boost(fm)
        if score > 0:
            scored.append((score, i))
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, i in scored[:limit]:
        p, text, fm = candidates[i]
        snip = " ".join(text.split())[:420]
        matched = _tokenize_light(query)
        out.append((score, p, fm, snip, matched))
    return out


def _get_persistent_cache(root: Path):
    """Open the SQLite index for embedding cache. Returns IndexDB or None."""
    try:
        import importlib.util as _ilu
        idx_path = root / ".agents" / "skills" / "internal-rag" / "irag_index.py"
        spec = _ilu.spec_from_file_location("irag_index", str(idx_path))
        if spec is None or spec.loader is None:
            return None
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.open_index(root)
    except Exception:
        return None


def _compute_content_hash_simple(text: str) -> str:
    """Simple content hash for embedding cache (SHA-256 of doc text)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dense_search_raw(query: str,
                     candidates: List[Tuple[Path, str, Dict[str, Any]]],
                     cfg: Dict[str, Any],
                     root: Path) -> Optional[List[Tuple[float, int]]]:
    """Raw dense retrieval — returns (cosine_similarity, candidate_index) pairs.
    No policy boosts, no limits, no snippets. Sorted by cosine descending.
    Returns None if embeddings are unavailable or disabled.
    Uses persistent SQLite embedding cache when available."""
    mode = str(cfg.get("retrieval", {}).get("embeddings", "auto")).lower()
    if mode in ("off", "no", "false", "0"):
        return None
    if not candidates:
        return []
    try:
        import numpy as np
    except Exception:
        return None
    model_name, query_prefix, passage_prefix = _resolve_model(cfg)
    model = _load_model(model_name)
    if model is None:
        return None
    try:
        docs = []
        chunk_ids = []
        content_hashes = []
        for p, text, fm in candidates:
            header = "\n".join(text.splitlines()[:40])
            body = " ".join(text.split())[:2000]
            doc_text = f"{p.relative_to(root)}\n{header}\n{body}"
            # Apply passage prefix for E5 models
            if passage_prefix:
                doc_text = passage_prefix + doc_text
            docs.append(doc_text)
            mem_id = str(fm.get("id", str(p)))
            chunk_ids.append(f"{mem_id}-c0")
            content_hashes.append(_compute_content_hash_simple(doc_text))

        # Query embedding (in-memory, not cached persistently)
        q_text = query
        if query_prefix:
            q_text = query_prefix + query
        q_emb = _embed(model, [q_text], model_key=model_name)[0]

        # Try persistent cache
        idx = _get_persistent_cache(root)
        cached_vectors: Dict[str, Any] = {}
        missing_indices: List[int] = []
        if idx is not None:
            cached = idx.get_embeddings_batch(chunk_ids, model_name, "float32")
            for i, cid in enumerate(chunk_ids):
                if cid in cached and cached[cid][1] == content_hashes[i]:
                    cached_vectors[cid] = cached[cid][0]
                else:
                    missing_indices.append(i)
        else:
            missing_indices = list(range(len(docs)))

        # Encode missing docs
        new_vectors: Dict[str, Any] = {}
        if missing_indices:
            missing_docs = [docs[i] for i in missing_indices]
            missing_embs = _embed(model, missing_docs, model_key=model_name)
            for j, i in enumerate(missing_indices):
                cid = chunk_ids[i]
                new_vectors[cid] = missing_embs[j]
                # Store in persistent cache
                if idx is not None:
                    try:
                        idx.set_embedding(cid, model_name, missing_embs[j],
                                          content_hashes[i])
                    except Exception:
                        pass

        # Assemble full embedding matrix
        all_embs = []
        for i, cid in enumerate(chunk_ids):
            if cid in cached_vectors:
                all_embs.append(np.asarray(cached_vectors[cid], dtype=np.float32))
            elif cid in new_vectors:
                all_embs.append(np.asarray(new_vectors[cid], dtype=np.float32))
            else:
                # Should not happen, but fallback to encode
                emb = _embed(model, [docs[i]], model_key=model_name)[0]
                all_embs.append(emb)

        d_emb = np.array(all_embs, dtype=np.float32)
        sims = (d_emb @ q_emb) if hasattr(d_emb, "@") else np.dot(d_emb, q_emb)
        scored: List[Tuple[float, int]] = []
        for i, sim in enumerate(sims):
            scored.append((float(sim), i))
        scored.sort(key=lambda x: -x[0])
        if idx is not None:
            idx.close()
        return scored
    except Exception:
        return None


def dense_similarity_matrix(candidate_indices: List[int],
                             candidates: List[Tuple[Path, str, Dict[str, Any]]],
                             cfg: Dict[str, Any],
                             root: Path) -> Optional[Any]:
    """Compute pairwise cosine similarity matrix for MMR diversity.
    Returns numpy matrix [n x n] or None if embeddings unavailable."""
    try:
        import numpy as np
    except Exception:
        return None
    model_name, _, passage_prefix = _resolve_model(cfg)
    model = _load_model(model_name)
    if model is None:
        return None
    try:
        docs = []
        for i in candidate_indices:
            p, text, fm = candidates[i]
            header = "\n".join(text.splitlines()[:40])
            body = " ".join(text.split())[:2000]
            doc_text = f"{p.relative_to(root)}\n{header}\n{body}"
            if passage_prefix:
                doc_text = passage_prefix + doc_text
            docs.append(doc_text)
        emb = _embed(model, docs, model_key=model_name)
        sims = emb @ emb.T if hasattr(emb, "T") else np.dot(emb, emb.T)
        return sims
    except Exception:
        return None