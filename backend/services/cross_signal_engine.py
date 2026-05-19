"""Cross-Signal Engine — turns a suspicious cluster into a PHANTOM score.

This is Engine 2's final verdict. For each suspicious cluster from Louvain,
we compute two component scores and combine them:

  behavioral_score  (cluster geometry + Upgrade A multi-signal evidence)
  origin_match_score  (do the documents claim to come from the same place?)
  phantom_score = 0.5 × behavioral + 0.5 × origin_match

The weights (per PHANTOM_MASTER_PLAN.md §14, locked-in form including Upgrade A):

  behavioral_score:
     timing_burst         × 0.24
     template_match       × 0.24
     cluster_size         × 0.12
     pii_overlap          × 0.15   (Upgrade A)
     text_similarity      × 0.15   (Upgrade A)
     name_similarity      × 0.10   (Upgrade A)
                          ──────
                            1.00

  origin_match_score:
     same_tool_fraction         × 0.50
     entropy_similarity         × 0.30
     font_hash_match_fraction   × 0.20
                                ──────
                                  1.00

Decision thresholds:
  phantom_score ≥ 0.85  → CONFIRMED RING → FREEZE_AND_ESCALATE
  phantom_score ≥ 0.65  → SUSPECTED RING → FLAG_FOR_REVIEW
  phantom_score < 0.65  → CLEAR

All component values are floats in [0, 1]. The output of this engine is a
ClusterVerdict — deterministic, reproducible, signable.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

import numpy as np
from loguru import logger

from schemas.origin_certificate import EntropyProfile, OriginCertificate
from schemas.phantom_report import RecommendedAction
from services.name_match import cluster_name_similarity_fraction
from services.pii_signals import (
    PIIFingerprint,
    cluster_pii_overlap_fraction,
)
from services.text_similarity import cluster_text_similarity_fraction

# Decision thresholds
PHANTOM_CONFIRMED_RING = 0.85
PHANTOM_SUSPECTED_RING = 0.65

# behavioral_score weights (sum to 1.0)
W_TIMING = 0.24
W_TEMPLATE = 0.24
W_CLUSTER_SIZE = 0.12
W_PII = 0.15
W_TEXT = 0.15
W_NAME = 0.10

# origin_match_score weights (sum to 1.0)
W_SAME_TOOL = 0.50
W_ENTROPY_SIM = 0.30
W_FONT_HASH = 0.20

# Misc tuning constants
TIMING_BURST_TIGHT = timedelta(minutes=10)
TIMING_BURST_LOOSE = timedelta(minutes=30)
CLUSTER_SIZE_SATURATION = 15  # cluster_size_score = min(N/15, 1.0)


# ---------------------------------------------------------------------------
# Per-component scoring functions
# ---------------------------------------------------------------------------


def _timing_burst_score(submission_times: list) -> float:
    if len(submission_times) < 2:
        return 0.0
    times_sorted = sorted(submission_times)
    span = times_sorted[-1] - times_sorted[0]
    if span < TIMING_BURST_TIGHT:
        return 1.0
    if span < TIMING_BURST_LOOSE:
        return 0.5
    return 0.0


def _template_match_fraction(font_subset_hashes: list[str | None]) -> float:
    """Fraction of cluster members sharing the most-common font_subset_hash."""
    non_null = [h for h in font_subset_hashes if h]
    if not non_null:
        return 0.0
    most_common_hash, count = Counter(non_null).most_common(1)[0]
    return count / len(font_subset_hashes)


def _cluster_size_score(n_members: int) -> float:
    if n_members <= 1:
        return 0.0
    return min(n_members / CLUSTER_SIZE_SATURATION, 1.0)


def _same_tool_fraction(origin_tools: list[str | None]) -> float:
    non_null = [t for t in origin_tools if t]
    if not non_null:
        return 0.0
    _, count = Counter(non_null).most_common(1)[0]
    return count / len(origin_tools)


def _entropy_similarity_mean(profiles: list[EntropyProfile]) -> float:
    """Mean pairwise cosine similarity of entropy profiles across the cluster.

    Result is in [0, 1] (clamped — cosine for these non-negative vectors
    stays in [0, 1] anyway).
    """
    if len(profiles) < 2:
        return 0.0
    sims: list[float] = []
    for i in range(len(profiles)):
        for j in range(i + 1, len(profiles)):
            sims.append(profiles[i].cosine_to(profiles[j]))
    mean = float(np.mean(sims)) if sims else 0.0
    return max(0.0, min(1.0, mean))


def _font_hash_match_fraction(font_subset_hashes: list[str | None]) -> float:
    # Same math as template_match_fraction — kept distinct for the report
    # so origin_match shows it as its own line item.
    return _template_match_fraction(font_subset_hashes)


# ---------------------------------------------------------------------------
# Per-cluster verdict
# ---------------------------------------------------------------------------


@dataclass
class ClusterVerdict:
    member_ids: list[UUID]

    # Component scores
    timing_burst_score: float
    template_match_fraction: float
    cluster_size_score: float
    pii_overlap_fraction: float
    text_similarity_fraction: float
    name_similarity_fraction: float

    same_tool_fraction: float
    entropy_similarity: float
    font_hash_match_fraction: float

    # Composite scores
    behavioral_score: float
    origin_match_score: float
    phantom_score: float

    recommended_action: RecommendedAction

    # Timing windows surfaced in the report
    submissions_from: object   # datetime; left untyped to avoid pydantic dep here
    submissions_to: object

    def as_dict(self) -> dict:
        return {
            "member_ids": [str(m) for m in self.member_ids],
            "timing_burst_score": round(self.timing_burst_score, 4),
            "template_match_fraction": round(self.template_match_fraction, 4),
            "cluster_size_score": round(self.cluster_size_score, 4),
            "pii_overlap_fraction": round(self.pii_overlap_fraction, 4),
            "text_similarity_fraction": round(self.text_similarity_fraction, 4),
            "name_similarity_fraction": round(self.name_similarity_fraction, 4),
            "same_tool_fraction": round(self.same_tool_fraction, 4),
            "entropy_similarity": round(self.entropy_similarity, 4),
            "font_hash_match_fraction": round(self.font_hash_match_fraction, 4),
            "behavioral_score": round(self.behavioral_score, 4),
            "origin_match_score": round(self.origin_match_score, 4),
            "phantom_score": round(self.phantom_score, 4),
            "recommended_action": self.recommended_action.value,
            "submissions_from": getattr(self.submissions_from, "isoformat", lambda: None)(),
            "submissions_to": getattr(self.submissions_to, "isoformat", lambda: None)(),
        }


def _decision(phantom_score: float) -> RecommendedAction:
    if phantom_score >= PHANTOM_CONFIRMED_RING:
        return RecommendedAction.FREEZE_AND_ESCALATE
    if phantom_score >= PHANTOM_SUSPECTED_RING:
        return RecommendedAction.FLAG_FOR_REVIEW
    return RecommendedAction.CLEAR


def score_cluster(
    member_ids: list[UUID],
    *,
    applicants_by_id: dict[UUID, dict],
    certificates_by_app: dict[UUID, OriginCertificate],
    embeddings_by_app: dict | None = None,
    pii_fingerprints_by_app: dict[UUID, PIIFingerprint] | None = None,
) -> ClusterVerdict:
    """Compute all component + composite scores for a single suspicious cluster.

    Inputs are dicts keyed by application_id so the caller can reuse them
    across multiple clusters in the same batch.
    """
    if not member_ids:
        raise ValueError("Cannot score an empty cluster")

    # Pull the slices for this cluster.
    submission_times = [
        applicants_by_id[m]["submission_time"] for m in member_ids if m in applicants_by_id
    ]
    certs = [certificates_by_app.get(m) for m in member_ids]
    font_hashes = [c.font_subset_hash if c else None for c in certs]
    origin_tools = [c.origin_tool if c else None for c in certs]
    profiles = [c.entropy_profile for c in certs if c is not None]

    # --- behavioral_score components ---
    timing = _timing_burst_score(submission_times)
    template = _template_match_fraction(font_hashes)
    cluster_size = _cluster_size_score(len(member_ids))

    # Upgrade A pieces — graceful zero if a sub-system is unavailable.
    if pii_fingerprints_by_app:
        pii_fp_list = [pii_fingerprints_by_app[m] for m in member_ids if m in pii_fingerprints_by_app]
        pii_frac = cluster_pii_overlap_fraction(pii_fp_list)
    else:
        pii_frac = 0.0

    if embeddings_by_app is not None:
        text_frac = cluster_text_similarity_fraction(embeddings_by_app, member_ids)
    else:
        text_frac = 0.0

    name_frac = cluster_name_similarity_fraction(
        [applicants_by_id[m].get("applicant_name") for m in member_ids if m in applicants_by_id]
    )

    behavioral = (
        timing * W_TIMING
        + template * W_TEMPLATE
        + cluster_size * W_CLUSTER_SIZE
        + pii_frac * W_PII
        + text_frac * W_TEXT
        + name_frac * W_NAME
    )

    # --- origin_match_score components ---
    tool_frac = _same_tool_fraction(origin_tools)
    entropy_sim = _entropy_similarity_mean(profiles)
    font_hash_frac = _font_hash_match_fraction(font_hashes)

    origin_match = (
        tool_frac * W_SAME_TOOL
        + entropy_sim * W_ENTROPY_SIM
        + font_hash_frac * W_FONT_HASH
    )

    phantom = 0.5 * behavioral + 0.5 * origin_match
    phantom = max(0.0, min(1.0, phantom))

    submissions_from = min(submission_times) if submission_times else None
    submissions_to = max(submission_times) if submission_times else None

    verdict = ClusterVerdict(
        member_ids=list(member_ids),
        timing_burst_score=timing,
        template_match_fraction=template,
        cluster_size_score=cluster_size,
        pii_overlap_fraction=pii_frac,
        text_similarity_fraction=text_frac,
        name_similarity_fraction=name_frac,
        same_tool_fraction=tool_frac,
        entropy_similarity=entropy_sim,
        font_hash_match_fraction=font_hash_frac,
        behavioral_score=behavioral,
        origin_match_score=origin_match,
        phantom_score=phantom,
        recommended_action=_decision(phantom),
        submissions_from=submissions_from,
        submissions_to=submissions_to,
    )

    logger.info(
        "Verdict | n={} | behav={:.3f} | origin={:.3f} | PHANTOM={:.3f} | action={}",
        len(member_ids),
        behavioral,
        origin_match,
        phantom,
        verdict.recommended_action.value,
    )
    return verdict
