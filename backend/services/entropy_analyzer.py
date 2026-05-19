"""Shannon entropy analyzer for raw PDF byte streams.

Why this matters: real Core Banking System PDFs have a characteristic byte
entropy profile — high entropy in middle sections (compressed image / object
streams) and lower entropy at start (header) and end (trailer + xref).
Consumer design tools like Canva produce flatter, less differentiated
profiles because they pack content differently.

We slice the file into 8 equal byte sections and compute Shannon entropy for
each. The 8-vector becomes a fingerprint we can compare across documents
and to the CBS reference corpus (Upgrade B, PHANTOM_MASTER_PLAN.md §14).
"""
from __future__ import annotations

import numpy as np
from loguru import logger
from scipy.stats import entropy as shannon_entropy

from schemas.origin_certificate import EntropyProfile

# Profile classification thresholds — see PHANTOM_MASTER_PLAN.md §"entropy_analyzer.py".
_CONSUMER_VARIANCE_MAX = 0.3
_CBS_VARIANCE_MIN = 0.8
_CBS_MEAN_MIN = 6.5

# Minimum useful file size — below this the per-section histogram is meaningless.
_MIN_BYTES_FOR_PROFILE = 256

_N_BUCKETS = 8


def _section_entropy(section: bytes) -> float:
    """Shannon entropy in bits/byte over a single section."""
    if not section:
        return 0.0
    counts = np.bincount(np.frombuffer(section, dtype=np.uint8), minlength=256)
    probs = counts / counts.sum()
    # base=2 → entropy in bits (range 0–8 for byte streams)
    return float(shannon_entropy(probs, base=2))


def _classify_profile(mean: float, variance: float) -> str:
    if variance < _CONSUMER_VARIANCE_MAX:
        return "consumer_like"
    if variance > _CBS_VARIANCE_MIN and mean > _CBS_MEAN_MIN:
        return "cbs_like"
    return "unknown"


def analyze_entropy(raw_bytes: bytes) -> EntropyProfile:
    """Return an 8-bucket entropy fingerprint for a PDF byte stream.

    Pure function. No file I/O, no network. Safe to run inside Celery workers
    in parallel.
    """
    n = len(raw_bytes)
    if n < _MIN_BYTES_FOR_PROFILE:
        logger.warning("PDF too small for entropy profile ({} bytes), returning zeros", n)
        return EntropyProfile(
            buckets=[0.0] * _N_BUCKETS,
            mean_entropy=0.0,
            entropy_variance=0.0,
            profile_type="unknown",
        )

    # Slice into 8 contiguous, non-overlapping byte sections.
    section_size = n // _N_BUCKETS
    buckets: list[float] = []
    for i in range(_N_BUCKETS):
        start = i * section_size
        # Last section absorbs any trailing bytes.
        end = n if i == _N_BUCKETS - 1 else start + section_size
        buckets.append(_section_entropy(raw_bytes[start:end]))

    arr = np.array(buckets, dtype=float)
    mean = float(arr.mean())
    variance = float(arr.var())
    profile_type = _classify_profile(mean, variance)

    logger.debug(
        "Entropy profile | mean={:.3f} | var={:.3f} | type={}",
        mean,
        variance,
        profile_type,
    )

    return EntropyProfile(
        buckets=[round(b, 4) for b in buckets],
        mean_entropy=round(mean, 4),
        entropy_variance=round(variance, 4),
        profile_type=profile_type,
    )
