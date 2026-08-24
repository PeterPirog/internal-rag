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


def _load_model(model_name: str):
    if model_name in _MODEL_CACHE:
        return _MODEL_CACHE[model_name]
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        return None
    try:
        model = SentenceTransformer(model_name)
    except Exception:
        try:
            model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception:
            return None
    _MODEL_CACHE[model_name] = model
    return model


def _embed(model, texts: List[str]):
    import numpy as np
    key = hashlib.sha256(("\n".join(texts)).encode("utf-8")).hexdigest()
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
    mode = str(cfg.get("retrieval", {}).get("embeddings", "auto")).lower()
    if mode in ("off", "no", "false", "0"):
        return None
    if not candidates:
        return []
    try:
        import numpy as np
    except Exception:
        return None
    model_name = str(cfg.get("retrieval", {}).get("embeddings_model", DEFAULT_MODEL))
    model = _load_model(model_name)
    if model is None:
        return None
    try:
        docs = []
        for p, text, fm in candidates:
            header = "\n".join(text.splitlines()[:40])
            body = " ".join(text.split())[:2000]
            docs.append(f"{p.relative_to(root)}\n{header}\n{body}")
        q_emb = _embed(model, [query])[0]
        d_emb = _embed(model, docs)
        sims = (d_emb @ q_emb) if hasattr(d_emb, "@") else np.dot(d_emb, q_emb)
        # Combine with status heuristic
        scored: List[Tuple[float, int]] = []
        for i, sim in enumerate(sims):
            fm = candidates[i][2]
            status = str(fm.get("status", "active")).lower()
            score = float(sim)
            if status == "active":
                score += 0.05
            elif status == "tentative":
                score += 0.02
            elif status == "superseded":
                score -= 0.2
            elif status in ("invalid", "archived"):
                score -= 10.0
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
    except Exception:
        return None