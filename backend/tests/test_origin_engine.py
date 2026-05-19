"""Smoke tests for services/origin_engine — the per-signal scoring functions.

These test the pure-function pieces without touching the full pipeline
(which would need a real PDF + ViT model). The point is to lock in that:

  * tool_category scoring penalises consumer tools and rewards CBS producers
  * font_subsetting scoring monotonically tracks the subsetting ratio
  * entropy scoring rewards CBS-like profiles when no reference corpus exists
  * the weight tables sum to 1.0 (so cbs_match_score never blows past 1.0)
"""
from __future__ import annotations

from datetime import datetime

import pytest

from schemas.origin_certificate import EntropyProfile, PDFMetadata, ToolCategory
from services.origin_engine import (
    WEIGHTS_FULL,
    WEIGHTS_NO_VIT,
    _score_entropy,
    _score_font_subsetting,
    _score_tool_category,
    _score_vit_embedding,
    compute_font_subset_hash,
)


def test_weight_tables_sum_to_one():
    assert abs(sum(WEIGHTS_FULL.values()) - 1.0) < 1e-9
    assert abs(sum(WEIGHTS_NO_VIT.values()) - 1.0) < 1e-9


def test_tool_category_penalises_consumer():
    canva = PDFMetadata(producer="Canva 2.0", tool_category=ToolCategory.CONSUMER_DESIGN_TOOL)
    finacle = PDFMetadata(producer="Finacle 7.3", tool_category=ToolCategory.CORE_BANKING_SYSTEM)
    assert _score_tool_category(canva, cbs_ref=None) < 0.2
    assert _score_tool_category(finacle, cbs_ref=None) > 0.9


def test_tool_category_neutral_for_office():
    word = PDFMetadata(producer="Microsoft Word", tool_category=ToolCategory.OFFICE_PRODUCTIVITY)
    score = _score_tool_category(word, cbs_ref=None)
    # Office docs are ambiguous — between consumer and CBS, closer to mid.
    assert 0.3 < score < 0.7


def test_font_subsetting_is_monotonic():
    """Higher subsetting ratio → higher score, period."""
    no_subsets = PDFMetadata(font_names=["Arial", "Helvetica"], subsetted_fonts=[])
    half = PDFMetadata(
        font_names=["Arial", "Helvetica"], subsetted_fonts=["AAAAAA+Arial"]
    )
    all_subsets = PDFMetadata(
        font_names=["Arial", "Helvetica"],
        subsetted_fonts=["AAAAAA+Arial", "BBBBBB+Helvetica"],
    )
    s0 = _score_font_subsetting(no_subsets)
    s1 = _score_font_subsetting(half)
    s2 = _score_font_subsetting(all_subsets)
    assert s0 < s1 < s2
    assert s0 == pytest.approx(0.0)
    assert s2 == pytest.approx(1.0)


def test_font_subsetting_handles_no_fonts():
    empty = PDFMetadata(font_names=[], subsetted_fonts=[])
    # Neutral — can't tell anything.
    assert _score_font_subsetting(empty) == 0.50


def test_entropy_fallback_rewards_cbs_like():
    """Without a reference corpus, we lean on the profile_type classification."""
    cbs_like = EntropyProfile(
        buckets=[7.5, 4.0, 7.8, 4.2, 7.6, 4.1, 7.9, 4.0],
        mean_entropy=5.8,
        entropy_variance=2.5,
        profile_type="cbs_like",
    )
    consumer = EntropyProfile(
        buckets=[6.0, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0],
        mean_entropy=6.0,
        entropy_variance=0.0,
        profile_type="consumer_like",
    )
    unknown = EntropyProfile(
        buckets=[5.0] * 8, mean_entropy=5.0, entropy_variance=0.0, profile_type="unknown"
    )
    assert _score_entropy(cbs_like, cbs_ref=None) > 0.8
    assert _score_entropy(consumer, cbs_ref=None) < 0.2
    assert _score_entropy(unknown, cbs_ref=None) == 0.50


def test_vit_score_none_when_embedding_missing():
    assert _score_vit_embedding(None, cbs_ref=None) is None


def test_vit_score_neutral_without_reference():
    """With an embedding but no CBS centroid, we return a neutral score."""
    embedding = [0.0] * 768
    embedding[0] = 1.0
    assert _score_vit_embedding(embedding, cbs_ref=None) == 0.50


def test_font_subset_hash_deterministic():
    """Same font list → same hash, regardless of order/case."""
    a = compute_font_subset_hash(["Arial", "Helvetica", "Times"])
    b = compute_font_subset_hash(["times", "ARIAL", "Helvetica"])
    assert a == b
    # Different list → different hash
    c = compute_font_subset_hash(["Arial", "Helvetica"])
    assert a != c
