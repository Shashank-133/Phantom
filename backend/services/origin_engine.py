"""Origin Engine — combines all signals into one weighted OriginCertificate.

This is the heart of Engine 1 (document origin intelligence). It produces a
single 0.0–1.0 `cbs_match_score` per document where:
  1.0 → fingerprint matches a genuine Core Banking System document
  0.0 → fingerprint matches a consumer design tool (Canva, Photoshop, etc.)

Signals & weights (PHANTOM_MASTER_PLAN.md §"origin_engine.py"):
  tool_category    0.35   from PDF /Producer + /Creator metadata
  entropy_profile  0.25   from Shannon entropy of raw bytes
  font_subsetting  0.20   from font subsetting ratio
  vit_embedding    0.20   from ViT CLS embedding cosine vs CBS centroid

Demo-safety: if ViT returns None (timeout / model missing), its 0.20 weight is
redistributed equally to the other three signals. The certificate's
`confidence` field drops accordingly so the UI can show "no ViT signal" badging.

CBS reference corpus (Upgrade B): when the synthetic CBS reference at
models/cbs_reference.pkl exists, ViT and entropy use real distance-to-centroid
math. When it doesn't yet (pre-Day 3), we fall back to heuristics flagged in
the code below so origin_engine still works for early development.
"""
from __future__ import annotations

import hashlib
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import imagehash
import numpy as np
from loguru import logger
from PIL import Image

from config import get_settings
from ml.vit_inference import VIT_EMBEDDING_DIM, extract_forensic_features
from schemas.origin_certificate import (
    EntropyProfile,
    OriginCertificate,
    PDFMetadata,
    ToolCategory,
)
from services.entropy_analyzer import analyze_entropy
from services.pdf_parser import ParsedPDF

# Signal weights — must sum to 1.0
WEIGHTS_FULL = {
    "tool_category": 0.35,
    "entropy_profile": 0.25,
    "font_subsetting": 0.20,
    "vit_embedding": 0.20,
}
# When ViT is unavailable, redistribute its 0.20 across the remaining 3.
WEIGHTS_NO_VIT = {
    "tool_category": 0.35 + 0.20 / 3,
    "entropy_profile": 0.25 + 0.20 / 3,
    "font_subsetting": 0.20 + 0.20 / 3,
}


@dataclass
class CBSReference:
    """Loaded from models/cbs_reference.pkl, built by seed/build_cbs_corpus.py.

    Populated on Day 3 (Upgrade B). Until then, origin_engine falls back to
    heuristic scoring marked with `# fallback:` comments.
    """

    mean_entropy_buckets: np.ndarray         # shape (8,)
    mean_vit_embedding: np.ndarray | None    # shape (768,), L2-normalized
    expected_font_subset_hashes: set[str]
    producer_whitelist: set[str]
    n_samples: int

    @classmethod
    def load(cls, path: Path) -> "CBSReference | None":
        if not path.exists():
            logger.debug("CBS reference not found at {} — using heuristic fallback", path)
            return None
        try:
            with path.open("rb") as f:
                obj = pickle.load(f)
            if not isinstance(obj, cls):
                logger.error("CBS reference file is not a CBSReference instance")
                return None
            logger.info("CBS reference loaded ({} samples)", obj.n_samples)
            return obj
        except Exception as e:
            logger.error("CBS reference load failed: {}", e)
            return None


_cbs_ref: CBSReference | None = None
_cbs_load_attempted = False


def _get_cbs_reference() -> CBSReference | None:
    """Lazy-load the CBS reference, once per process."""
    global _cbs_ref, _cbs_load_attempted
    if _cbs_load_attempted:
        return _cbs_ref
    _cbs_load_attempted = True
    settings = get_settings()
    _cbs_ref = CBSReference.load(settings.models_path / "cbs_reference.pkl")
    return _cbs_ref


# ---------------------------------------------------------------------------
# Per-signal scoring functions — each returns a float in [0.0, 1.0] where
# higher = more CBS-like.
# ---------------------------------------------------------------------------


def _score_tool_category(metadata: PDFMetadata, cbs_ref: CBSReference | None) -> float:
    if metadata.tool_category == ToolCategory.CORE_BANKING_SYSTEM:
        # Bonus if the exact producer is in our reference whitelist.
        if cbs_ref and metadata.producer:
            if any(p.lower() in metadata.producer.lower() for p in cbs_ref.producer_whitelist):
                return 1.0
        return 0.95
    if metadata.tool_category == ToolCategory.OFFICE_PRODUCTIVITY:
        return 0.55  # ambiguous — could be legit, could be fake
    if metadata.tool_category == ToolCategory.CONSUMER_DESIGN_TOOL:
        return 0.05
    return 0.50  # unknown = neutral


def _score_entropy(profile: EntropyProfile, cbs_ref: CBSReference | None) -> float:
    if cbs_ref is not None and cbs_ref.mean_entropy_buckets is not None:
        # Real measurement: cosine similarity to the CBS reference profile.
        doc = np.array(profile.buckets, dtype=float)
        ref = cbs_ref.mean_entropy_buckets
        denom = (np.linalg.norm(doc) * np.linalg.norm(ref)) or 1.0
        sim = float(np.dot(doc, ref) / denom)
        # cosine ∈ [-1, 1] → map to [0, 1]
        return max(0.0, min(1.0, (sim + 1.0) / 2.0))

    # fallback: profile_type classification → score
    if profile.profile_type == "cbs_like":
        return 0.90
    if profile.profile_type == "consumer_like":
        return 0.10
    return 0.50


def _score_font_subsetting(metadata: PDFMetadata) -> float:
    """High subsetting ratio = CBS-like. Canva/Photoshop usually don't subset."""
    ratio = metadata.font_subsetting_ratio
    if not metadata.font_names:
        return 0.50  # can't tell — no fonts found
    # Sharper curve: 0% = 0.0, 50% = 0.5, 100% = 1.0
    return round(ratio, 3)


def _score_vit_embedding(
    embedding: list[float] | None, cbs_ref: CBSReference | None
) -> float | None:
    if embedding is None:
        return None
    if cbs_ref is None or cbs_ref.mean_vit_embedding is None:
        # fallback: no centroid yet → neutral but valid score
        return 0.50

    e = np.array(embedding, dtype=float)
    ref = cbs_ref.mean_vit_embedding
    # both are L2-normalized → dot product is cosine similarity in [-1, 1]
    sim = float(np.dot(e, ref))
    return max(0.0, min(1.0, (sim + 1.0) / 2.0))


# ---------------------------------------------------------------------------
# Public API — what workers/tasks.py calls.
# ---------------------------------------------------------------------------


def compute_font_subset_hash(font_names: list[str]) -> str:
    """MD5 of the sorted, lowercase font name list.

    Two documents using the same exact font set produce the same hash — that's
    the strongest "same template" signal we have. Drives TEMPLATE_MATCH edges
    in the Neo4j graph (Day 4).
    """
    normalized = sorted(name.lower().strip() for name in font_names)
    return hashlib.md5("|".join(normalized).encode()).hexdigest()


def compute_perceptual_hash(image: Image.Image) -> str:
    """64-bit perceptual hash of the page-0 render.

    Detects "visually identical" pages even after minor edits. Drives
    TEMPLATE_MATCH edges when Hamming distance < 10.
    """
    return str(imagehash.phash(image, hash_size=8))


def score_document(
    parsed: ParsedPDF,
    *,
    application_id: UUID,
    doc_id: UUID | None = None,
    use_vit: bool = True,
) -> OriginCertificate:
    """Produce a complete OriginCertificate from a parsed PDF.

    Calls (in order):
      1. analyze_entropy(raw_bytes) — services/entropy_analyzer.py
      2. extract_forensic_features(page0) — ml/vit_inference.py, with timeout
      3. perceptual_hash(page0) — imagehash.phash
      4. weighted combination → cbs_match_score
    """
    cbs_ref = _get_cbs_reference()

    # 1. entropy
    entropy_profile = analyze_entropy(parsed.raw_bytes)

    # 2. ViT (best-effort; None on failure)
    vit_embedding = extract_forensic_features(parsed.page0_image) if use_vit else None
    if use_vit and vit_embedding is None:
        logger.info("ViT unavailable for application {} — using no-ViT weights", application_id)

    # 3. perceptual hash (cheap, never fails)
    phash = compute_perceptual_hash(parsed.page0_image)

    # 4. per-signal scores
    s_tool = _score_tool_category(parsed.metadata, cbs_ref)
    s_entropy = _score_entropy(entropy_profile, cbs_ref)
    s_font = _score_font_subsetting(parsed.metadata)
    s_vit = _score_vit_embedding(vit_embedding, cbs_ref)

    # 5. weighted combine
    if s_vit is None:
        w = WEIGHTS_NO_VIT
        cbs_match_score = (
            s_tool * w["tool_category"]
            + s_entropy * w["entropy_profile"]
            + s_font * w["font_subsetting"]
        )
        # Lower confidence — we're missing the 0.20 ViT signal
        confidence = 0.70
    else:
        w = WEIGHTS_FULL
        cbs_match_score = (
            s_tool * w["tool_category"]
            + s_entropy * w["entropy_profile"]
            + s_font * w["font_subsetting"]
            + s_vit * w["vit_embedding"]
        )
        # Confidence boosted when signals agree; penalized when they disagree.
        signal_values = [s_tool, s_entropy, s_font, s_vit]
        signal_std = float(np.std(signal_values))
        confidence = max(0.50, 1.0 - signal_std)

    cbs_match_score = max(0.0, min(1.0, cbs_match_score))

    # 6. assemble the cert
    cert = OriginCertificate(
        doc_id=doc_id or uuid4(),
        application_id=application_id,
        cbs_match_score=round(cbs_match_score, 4),
        origin_tool=_friendly_tool_name(parsed.metadata),
        tool_category=parsed.metadata.tool_category,
        confidence=round(confidence, 4),
        font_subset_hash=compute_font_subset_hash(parsed.metadata.font_names),
        entropy_profile=entropy_profile,
        perceptual_hash=phash,
        vit_embedding=vit_embedding,
        pdf_metadata=parsed.metadata,
        creation_timestamp=parsed.metadata.creation_date,
    )

    logger.info(
        "Origin cert | app={} | cbs={:.3f} | conf={:.3f} | tool={!r} | vit={}",
        application_id,
        cert.cbs_match_score,
        cert.confidence,
        cert.origin_tool,
        "yes" if vit_embedding else "no",
    )
    return cert


def _friendly_tool_name(metadata: PDFMetadata) -> str:
    """Best human-readable label for the origin tool. Used in the UI badge."""
    parts = [s for s in (metadata.producer, metadata.creator) if s]
    if not parts:
        return "Unknown"
    # Producer is usually more informative than creator — prefer it if present.
    return metadata.producer or metadata.creator or "Unknown"


# ---------------------------------------------------------------------------
# Diagnostics — exposed for /health and tests, not on the demo critical path.
# ---------------------------------------------------------------------------


def diagnostics() -> dict[str, Any]:
    cbs = _get_cbs_reference()
    return {
        "cbs_reference_loaded": cbs is not None,
        "cbs_reference_samples": cbs.n_samples if cbs else 0,
        "vit_embedding_dim": VIT_EMBEDDING_DIM,
        "weights_full": WEIGHTS_FULL,
        "weights_no_vit": WEIGHTS_NO_VIT,
    }
