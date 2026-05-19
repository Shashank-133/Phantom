"""Smoke tests for services/cross_signal_engine.score_cluster.

The pipeline's whole credibility rests on this function producing a
deterministic, in-range PHANTOM score. We construct two synthetic clusters —
one that looks like the seeded fraud ring, one that looks like genuine
applicants — and assert the engine separates them correctly.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import numpy as np
import pytest

from schemas.origin_certificate import (
    EntropyProfile,
    OriginCertificate,
    PDFMetadata,
    ToolCategory,
)
from schemas.phantom_report import RecommendedAction
from services.cross_signal_engine import (
    PHANTOM_CONFIRMED_RING,
    PHANTOM_SUSPECTED_RING,
    score_cluster,
)
from services.pii_signals import fingerprint as pii_fingerprint


def _make_cert(
    app_id,
    *,
    cbs_match_score: float,
    origin_tool: str,
    font_hash: str,
    entropy_buckets: list[float],
) -> OriginCertificate:
    return OriginCertificate(
        doc_id=uuid4(),
        application_id=app_id,
        cbs_match_score=cbs_match_score,
        origin_tool=origin_tool,
        tool_category=(
            ToolCategory.CONSUMER_DESIGN_TOOL
            if "Canva" in origin_tool
            else ToolCategory.CORE_BANKING_SYSTEM
        ),
        confidence=0.85,
        font_subset_hash=font_hash,
        entropy_profile=EntropyProfile(
            buckets=entropy_buckets,
            mean_entropy=float(np.mean(entropy_buckets)),
            entropy_variance=float(np.var(entropy_buckets)),
            profile_type=(
                "consumer_like" if "Canva" in origin_tool else "cbs_like"
            ),
        ),
        perceptual_hash="ffffffffffffffff",
        pdf_metadata=PDFMetadata(
            producer=origin_tool,
            tool_category=(
                ToolCategory.CONSUMER_DESIGN_TOOL
                if "Canva" in origin_tool
                else ToolCategory.CORE_BANKING_SYSTEM
            ),
        ),
    )


@pytest.fixture
def fraud_ring_cluster():
    """Eleven near-identical applicants — same Canva template, 6-min burst,
    shared phone prefix, near-duplicate names, identical 'small business
    expansion' purpose."""
    base = datetime(2025, 8, 14, 10, 32, 0)
    names = [
        "Rahul Sharma", "Rahul Sharrma", "Sandeep Patil", "Sandip Patil",
        "Ankit Verma", "Priya Singh", "Vikram Yadav", "Arjun Reddy",
        "Neha Gupta", "Manish Kumar", "Suresh Iyer",
    ]
    member_ids = [uuid4() for _ in names]
    applicants_by_id = {}
    certs_by_app = {}
    pii_fps = {}

    for i, (mid, name) in enumerate(zip(member_ids, names)):
        applicants_by_id[mid] = {
            "id": mid,
            "application_id": mid,
            "applicant_name": name,
            "phone": f"+91 98765-{43000 + i:05d}",
            "email": f"applicant{i}@gmail.com",
            "bank_account": f"112233{i:04d}",
            "ifsc": "HDFC0001234",
            "pan": f"ABCDE{1234 + i}P",
            "purpose_of_loan": "small business expansion",
            "submission_time": base + timedelta(seconds=i * 35),
        }
        certs_by_app[mid] = _make_cert(
            mid,
            cbs_match_score=0.40,
            origin_tool="Canva 2.0",
            font_hash="canva-template-hash-A",
            entropy_buckets=[6.0, 6.1, 6.0, 5.9, 6.0, 6.0, 5.9, 6.1],
        )
        pii_fps[mid] = pii_fingerprint(applicants_by_id[mid])

    return member_ids, applicants_by_id, certs_by_app, pii_fps


@pytest.fixture
def innocent_cluster():
    """Five unrelated genuine applicants — different banks, scattered timing,
    distinct fonts."""
    base = datetime(2025, 8, 1, 10, 0, 0)
    names = ["Aarav Desai", "Ishita Bose", "Karan Mehta", "Sneha Kapoor", "Ravi Pillai"]
    member_ids = [uuid4() for _ in names]
    applicants_by_id = {}
    certs_by_app = {}
    pii_fps = {}
    tools = ["Finacle 7.3", "TCS BaNCS 9.1", "Oracle FLEXCUBE 12.4", "Temenos T24", "Finacle 7.3"]
    purposes = [
        "home renovation", "auto loan", "education loan",
        "business working capital", "wedding expenses",
    ]

    for i, (mid, name) in enumerate(zip(member_ids, names)):
        applicants_by_id[mid] = {
            "id": mid,
            "application_id": mid,
            "applicant_name": name,
            "phone": f"+91 {91000 + i * 1000}{i:05d}",
            "email": f"{name.split()[0].lower()}@example.com",
            "bank_account": f"{i:06d}123456",
            "ifsc": f"BANK000{i}",
            "pan": f"XYZAB{9000 + i}Z",
            "purpose_of_loan": purposes[i],
            "submission_time": base + timedelta(hours=i * 6),
        }
        certs_by_app[mid] = _make_cert(
            mid,
            cbs_match_score=0.90,
            origin_tool=tools[i],
            font_hash=f"hash-{i}-unique",
            entropy_buckets=[7.5, 4.0, 7.8, 4.2, 7.6, 4.1, 7.9, 4.0],
        )
        pii_fps[mid] = pii_fingerprint(applicants_by_id[mid])

    return member_ids, applicants_by_id, certs_by_app, pii_fps


def test_fraud_ring_scores_above_confirmed_threshold(fraud_ring_cluster):
    member_ids, applicants, certs, pii = fraud_ring_cluster
    verdict = score_cluster(
        member_ids,
        applicants_by_id=applicants,
        certificates_by_app=certs,
        embeddings_by_app=None,
        pii_fingerprints_by_app=pii,
    )
    assert verdict.phantom_score >= PHANTOM_CONFIRMED_RING, (
        f"Synthetic fraud ring scored {verdict.phantom_score:.3f}, expected ≥ {PHANTOM_CONFIRMED_RING}"
    )
    assert verdict.recommended_action == RecommendedAction.FREEZE_AND_ESCALATE
    assert verdict.timing_burst_score == 1.0
    assert verdict.template_match_fraction == 1.0
    assert verdict.same_tool_fraction == 1.0
    assert verdict.font_hash_match_fraction == 1.0
    # Name-similarity catches "Sharma/Sharrma" + "Sandeep/Sandip"
    assert verdict.name_similarity_fraction > 0.0


def test_innocent_cluster_scores_clear(innocent_cluster):
    member_ids, applicants, certs, pii = innocent_cluster
    verdict = score_cluster(
        member_ids,
        applicants_by_id=applicants,
        certificates_by_app=certs,
        embeddings_by_app=None,
        pii_fingerprints_by_app=pii,
    )
    assert verdict.phantom_score < PHANTOM_SUSPECTED_RING, (
        f"Innocent cluster scored {verdict.phantom_score:.3f}, expected < {PHANTOM_SUSPECTED_RING}"
    )
    assert verdict.recommended_action == RecommendedAction.CLEAR
    assert verdict.timing_burst_score == 0.0  # scattered across hours
    assert verdict.template_match_fraction < 0.5  # all unique font hashes


def test_phantom_score_always_in_unit_interval(fraud_ring_cluster, innocent_cluster):
    for fixture in (fraud_ring_cluster, innocent_cluster):
        member_ids, applicants, certs, pii = fixture
        verdict = score_cluster(
            member_ids,
            applicants_by_id=applicants,
            certificates_by_app=certs,
            pii_fingerprints_by_app=pii,
        )
        assert 0.0 <= verdict.behavioral_score <= 1.0
        assert 0.0 <= verdict.origin_match_score <= 1.0
        assert 0.0 <= verdict.phantom_score <= 1.0


def test_empty_cluster_raises():
    with pytest.raises(ValueError):
        score_cluster(
            [],
            applicants_by_id={},
            certificates_by_app={},
        )


def test_separation_gap(fraud_ring_cluster, innocent_cluster):
    """The whole demo's credibility rests on a wide gap between the two."""
    fraud_v = score_cluster(
        fraud_ring_cluster[0],
        applicants_by_id=fraud_ring_cluster[1],
        certificates_by_app=fraud_ring_cluster[2],
        pii_fingerprints_by_app=fraud_ring_cluster[3],
    )
    innocent_v = score_cluster(
        innocent_cluster[0],
        applicants_by_id=innocent_cluster[1],
        certificates_by_app=innocent_cluster[2],
        pii_fingerprints_by_app=innocent_cluster[3],
    )
    gap = fraud_v.phantom_score - innocent_v.phantom_score
    # If the gap collapses below 0.4 we lose visual separation in the demo.
    assert gap > 0.4, f"Fraud-vs-innocent gap {gap:.3f} is too narrow"
