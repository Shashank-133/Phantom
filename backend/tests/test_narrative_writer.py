"""Smoke tests for services/narrative_writer.

Critical guarantees we lock in:
  * Template always returns a non-empty string for any verdict.
  * The 4 hard facts (ring size, exposure, confidence %, recommended action)
    appear verbatim in the output.
  * Gemini is OFF when no API key is set, and `build_narrative` falls back to
    the template silently.
"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from schemas.phantom_report import RecommendedAction, RingMember
from services.cross_signal_engine import ClusterVerdict
from services.narrative_writer import (
    _template_narrative,
    build_narrative,
    narrative_source_info,
)


def _make_verdict(action: RecommendedAction, phantom_score: float) -> ClusterVerdict:
    return ClusterVerdict(
        member_ids=[uuid4() for _ in range(11)],
        timing_burst_score=1.0,
        template_match_fraction=1.0,
        cluster_size_score=0.73,
        pii_overlap_fraction=0.6,
        text_similarity_fraction=0.7,
        name_similarity_fraction=0.18,
        same_tool_fraction=1.0,
        entropy_similarity=0.95,
        font_hash_match_fraction=1.0,
        behavioral_score=0.9,
        origin_match_score=0.84,
        phantom_score=phantom_score,
        recommended_action=action,
        submissions_from=datetime(2025, 8, 14, 10, 32),
        submissions_to=datetime(2025, 8, 14, 10, 38),
    )


def _make_members(n: int) -> list[RingMember]:
    cities = ["Mumbai", "Pune", "Nagpur"]
    return [
        RingMember(
            application_id=uuid4(),
            applicant_name=f"Test Applicant {i}",
            city=cities[i % len(cities)],
            loan_amount_inr=5_000_000 + i * 200_000,
            submission_time=datetime(2025, 8, 14, 10, 32, i * 5),
            cbs_match_score=0.40,
            origin_tool="Canva 2.0",
            font_subset_hash="abc123",
        )
        for i in range(n)
    ]


def test_template_freeze_includes_hard_facts():
    verdict = _make_verdict(RecommendedAction.FREEZE_AND_ESCALATE, 0.877)
    members = _make_members(11)
    text = _template_narrative(verdict, members, "Origin summary.", "Timing summary.")
    assert "11 applicants" in text
    assert "Mumbai" in text and "Pune" in text and "Nagpur" in text
    assert "87.7%" in text
    assert "freeze" in text.lower() and "escalation" in text.lower()
    assert "Origin summary." in text
    assert "Timing summary." in text


def test_template_flag_uses_review_phrase():
    verdict = _make_verdict(RecommendedAction.FLAG_FOR_REVIEW, 0.72)
    text = _template_narrative(verdict, _make_members(5), "O.", "T.")
    assert "review" in text.lower()
    assert "freeze" not in text.lower()


def test_template_clear_uses_monitoring_phrase():
    verdict = _make_verdict(RecommendedAction.CLEAR, 0.40)
    text = _template_narrative(verdict, _make_members(3), "O.", "T.")
    assert "monitoring" in text.lower()


def test_build_narrative_falls_back_when_no_api_key(monkeypatch):
    """No GEMINI_API_KEY → template path is taken with no errors."""
    monkeypatch.setenv("GEMINI_API_KEY", "")
    # Reset cached settings + gemini state from prior tests
    from config import get_settings
    from services import narrative_writer as nw

    get_settings.cache_clear()
    nw._gemini_state["configured"] = False
    nw._gemini_state["model"] = None

    verdict = _make_verdict(RecommendedAction.FREEZE_AND_ESCALATE, 0.88)
    text = build_narrative(verdict, _make_members(11), "O.", "T.")
    assert text  # non-empty
    assert "11 applicants" in text


def test_narrative_source_info_reports_backend(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    from config import get_settings

    get_settings.cache_clear()
    info = narrative_source_info()
    assert info["backend"] == "template"
    assert info["gemini_available"] is False


def test_template_with_one_city():
    """Cities-list join shouldn't produce 'A and ' when all members share one city."""
    verdict = _make_verdict(RecommendedAction.FREEZE_AND_ESCALATE, 0.9)
    members = [
        RingMember(
            application_id=uuid4(),
            applicant_name=f"App {i}",
            city="Mumbai",
            loan_amount_inr=1_000_000,
            submission_time=datetime(2025, 1, 1),
            cbs_match_score=0.4,
            origin_tool="Canva",
            font_subset_hash="x",
        )
        for i in range(3)
    ]
    text = _template_narrative(verdict, members, "o", "t")
    assert "Mumbai" in text
    assert "Mumbai and Mumbai" not in text
