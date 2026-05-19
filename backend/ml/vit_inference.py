"""ViT feature extractor — google/vit-base-patch16-224 as a FEATURE EXTRACTOR only.

NOT a classifier. We do NOT use the ImageNet head. We extract the 768-dim CLS
token embedding from the last transformer hidden layer. This vector is the
"visual fingerprint" of how a document was rendered — typography, layout,
spacing, color, anti-aliasing — all the things that differ between a Canva
salary slip and a Finacle-generated one even when the text is identical.

Demo-safety contract:
  1. Models are pre-downloaded by backend/download_models.py.
  2. Inference runs on CPU. Each call has a hard timeout (default 15s).
  3. On timeout, model-missing, or any exception: return None. Caller must
     redistribute the ViT weight to other signals (see origin_engine.py).

The model is loaded ONCE, on first call, and cached at module level.
"""
from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

from loguru import logger
from PIL import Image

from config import get_settings

VIT_EMBEDDING_DIM = 768
_MODEL_NAME = "google/vit-base-patch16-224"
_DEFAULT_TIMEOUT_SECONDS = 15.0

_model: Any = None
_processor: Any = None
_load_lock = threading.Lock()
_load_failed: bool = False  # latch — don't keep retrying a failed load
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vit")


def _ensure_offline_env() -> None:
    """Force HF libs to look ONLY at the local cache. Demo must never hit the network."""
    settings = get_settings()
    models_dir = str(settings.models_path)
    # Use direct assignment (not setdefault) so a stale relative path from
    # a parent process can't shadow the resolved absolute path.
    os.environ["TRANSFORMERS_CACHE"] = models_dir
    os.environ["HF_HOME"] = models_dir
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def _load_model() -> bool:
    """Load model + processor once. Returns True on success, False on failure.

    Thread-safe. The first caller does the heavy work; concurrent callers wait
    on the lock then see the cached result.
    """
    global _model, _processor, _load_failed

    if _model is not None and _processor is not None:
        return True
    if _load_failed:
        return False

    with _load_lock:
        if _model is not None and _processor is not None:
            return True
        if _load_failed:
            return False

        _ensure_offline_env()
        try:
            # Imported lazily — these are 500+ MB worth of imports.
            import torch
            from transformers import ViTImageProcessor, ViTModel

            settings = get_settings()
            cache_dir = str(settings.models_path)

            logger.info("Loading ViT model from cache_dir={} (one-time)", cache_dir)
            _processor = ViTImageProcessor.from_pretrained(
                _MODEL_NAME, cache_dir=cache_dir, local_files_only=True
            )
            model = ViTModel.from_pretrained(
                _MODEL_NAME, cache_dir=cache_dir, local_files_only=True
            )
            model.eval()
            # Stay on CPU. GPU would be nice but we contract for laptop demos.
            torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))
            _model = model
            logger.info("ViT model ready (CPU)")
            return True

        except Exception as e:
            logger.error(
                "ViT load failed — vit_embedding will be None for all docs. "
                "Run `python backend/download_models.py` first. Cause: {}",
                e,
            )
            _load_failed = True
            _model = None
            _processor = None
            return False


def _infer_sync(pil_image: Image.Image) -> list[float]:
    """Synchronous inference. Runs inside the timeout-wrapping executor."""
    import torch

    img = pil_image.convert("RGB") if pil_image.mode != "RGB" else pil_image

    inputs = _processor(images=img, return_tensors="pt")  # type: ignore[union-attr]
    with torch.no_grad():
        outputs = _model(**inputs)  # type: ignore[misc]

    # last_hidden_state shape: (batch, seq_len, hidden_dim).
    # The CLS token is at position 0 — this is the standard ViT feature vector.
    cls = outputs.last_hidden_state[0, 0, :]
    # L2-normalize so cosine similarity reduces to a dot product downstream.
    cls = cls / (cls.norm() + 1e-12)
    return cls.cpu().tolist()


def extract_forensic_features(
    pil_image: Image.Image,
    *,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> list[float] | None:
    """Return a 768-dim L2-normalized embedding, or None if anything goes wrong.

    Demo-safety: callers MUST handle the None case. The origin_engine
    redistributes the 0.20 ViT weight to other signals when this returns None.
    """
    if not _load_model():
        return None

    future = _executor.submit(_infer_sync, pil_image)
    try:
        embedding = future.result(timeout=timeout_seconds)
    except FuturesTimeout:
        logger.warning(
            "ViT inference exceeded {}s — returning None (graceful fallback)",
            timeout_seconds,
        )
        future.cancel()
        return None
    except Exception as e:
        logger.error("ViT inference failed: {}", e)
        return None

    if len(embedding) != VIT_EMBEDDING_DIM:
        logger.error(
            "ViT returned unexpected dim {} (expected {})",
            len(embedding),
            VIT_EMBEDDING_DIM,
        )
        return None

    return embedding


def is_ready() -> bool:
    """For /health endpoint — has the model been loaded successfully?"""
    return _model is not None and _processor is not None and not _load_failed


def preload() -> bool:
    """Called from main.py lifespan to warm the model into memory at startup."""
    return _load_model()
