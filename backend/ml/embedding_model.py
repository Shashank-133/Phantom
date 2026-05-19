"""Sentence-transformer embedding model — all-MiniLM-L6-v2.

Why this model:
  - 90 MB, runs in ~0.1s per document on CPU
  - 384-dim output (small enough that pairwise cosine across 40 docs is trivial)
  - Strong general-purpose semantic similarity quality

Used by services/text_similarity.py to score Upgrade A's TEXT_MATCH edges
(free-text fields like purpose_of_loan, employer_description, address_line_2).

Lazy-loaded at first call. The model is small enough that we don't bother
with timeout guards — if it fails to load, callers get None and proceed.
"""
from __future__ import annotations

import os
import threading
from typing import Any

import numpy as np
from loguru import logger

from config import get_settings

EMBEDDING_DIM = 384
_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_model: Any = None
_load_lock = threading.Lock()
_load_failed: bool = False


def _ensure_offline_env() -> None:
    settings = get_settings()
    sbert_dir = str(settings.sentence_transformers_path)
    models_dir = str(settings.models_path)
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = sbert_dir
    os.environ["HF_HOME"] = models_dir
    os.environ["TRANSFORMERS_CACHE"] = models_dir
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def _load() -> bool:
    global _model, _load_failed
    if _model is not None:
        return True
    if _load_failed:
        return False

    with _load_lock:
        if _model is not None:
            return True
        if _load_failed:
            return False

        _ensure_offline_env()
        try:
            from sentence_transformers import SentenceTransformer

            settings = get_settings()
            logger.info("Loading sentence-transformer {} (one-time)", _MODEL_NAME)
            _model = SentenceTransformer(
                _MODEL_NAME,
                cache_folder=str(settings.models_path),
            )
            logger.info("Sentence-transformer ready")
            return True
        except Exception as e:
            logger.error(
                "Sentence-transformer load failed — TEXT_MATCH signal disabled. "
                "Run `python backend/download_models.py` first. Cause: {}",
                e,
            )
            _load_failed = True
            _model = None
            return False


def embed(text: str) -> np.ndarray | None:
    """Embed a single string into a 384-dim L2-normalized numpy vector.

    Returns None if the model is unavailable. Empty / whitespace-only input
    returns a zero vector (so cosine similarity to anything is 0.0).
    """
    if not _load():
        return None
    if not text or not text.strip():
        return np.zeros(EMBEDDING_DIM, dtype=np.float32)
    vec = _model.encode(text, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vec, dtype=np.float32)


def embed_batch(texts: list[str]) -> np.ndarray | None:
    """Embed many strings at once. Returns shape (N, 384) or None on failure."""
    if not _load():
        return None
    if not texts:
        return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)

    # Replace empty strings with a single space so the model doesn't choke.
    cleaned = [t if (t and t.strip()) else " " for t in texts]
    vecs = _model.encode(cleaned, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vecs, dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity assuming both vectors are L2-normalized → just a dot product."""
    return float(np.dot(a, b))


def preload() -> bool:
    """Used by main.py lifespan to warm the model at startup."""
    return _load()


def is_ready() -> bool:
    return _model is not None and not _load_failed
