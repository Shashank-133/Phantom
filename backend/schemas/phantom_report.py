"""PHANTOM Report — the final court-ready evidence bundle.

Produced by services/report_generator.py once cross_signal_engine has
confirmed a suspicious Louvain cluster crosses the confidence threshold.
Signed with Ed25519 (crypto/signer.py) so the bundle is tamper-evident.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RecommendedAction(str, Enum):
    FREEZE_AND_ESCALATE = "FREEZE_AND_ESCALATE"  # phantom_score >= 0.85
    FLAG_FOR_REVIEW = "FLAG_FOR_REVIEW"          # 0.65 <= phantom_score < 0.85
    CLEAR = "CLEAR"                              # phantom_score < 0.65


class RingMember(BaseModel):
    """One applicant inside a confirmed fraud ring."""

    application_id: UUID
    applicant_name: str
    city: str
    loan_amount_inr: int
    submission_time: datetime
    cbs_match_score: float
    origin_tool: str
    font_subset_hash: str


class EvidenceBundle(BaseModel):
    """The raw evidence used to compute the PHANTOM score.

    This is the structure that gets canonical-JSON-serialized and Ed25519-signed.
    Tampering with any field invalidates the signature.
    """

    model_config = ConfigDict(from_attributes=True)

    ring_id: str
    detected_at: datetime
    members: list[RingMember]

    # Component scores (each 0.0-1.0).
    behavioral_score: float = Field(..., ge=0.0, le=1.0)
    origin_match_score: float = Field(..., ge=0.0, le=1.0)
    phantom_score: float = Field(..., ge=0.0, le=1.0)

    # Component breakdown — exposed so the report can show "why".
    timing_burst_score: float
    template_match_fraction: float
    cluster_size_score: float
    same_tool_fraction: float
    entropy_similarity: float
    font_hash_match_fraction: float

    # Upgrade A (multi-signal) additions — populated when Day 4 lands.
    pii_overlap_fraction: float = 0.0
    text_similarity_fraction: float = 0.0
    name_similarity_fraction: float = 0.0

    # Timing window for the report timeline section.
    documents_created_from: datetime | None = None
    documents_created_to: datetime | None = None
    submissions_from: datetime
    submissions_to: datetime


class PHANTOMReport(BaseModel):
    """The final report object delivered to the frontend and PDF generator."""

    model_config = ConfigDict(from_attributes=True)

    ring_id: str
    ring_size: int
    total_exposure_inr: int
    phantom_confidence_pct: float = Field(..., ge=0.0, le=100.0)

    # The signed evidence — bundle JSON + Ed25519 signature + public key id.
    evidence_bundle: EvidenceBundle
    evidence_hash_sha256: str        # canonical-JSON SHA-256 (for quick eyeballing)
    evidence_signature_ed25519: str  # base64 Ed25519 signature
    signing_key_id: str              # short public-key fingerprint

    # Human-readable summaries for the report UI panel.
    origin_summary: str    # "All 11 members generated documents on Canva..."
    timing_summary: str    # "Submissions clustered in a 6-minute window..."
    narrative: str         # Full paragraph (template by default, Gemini optional)

    recommended_action: RecommendedAction
    generated_at: datetime = Field(default_factory=datetime.utcnow)
