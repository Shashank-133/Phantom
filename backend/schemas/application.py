"""Loan application schemas.

An Application is a single applicant + their submitted documents. PHANTOM
analyzes 40 of these per demo batch and looks for fraud rings across them.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class DocumentType(str, Enum):
    SALARY_SLIP = "salary_slip"
    BANK_STATEMENT = "bank_statement"
    ID_PROOF = "id_proof"
    ADDRESS_PROOF = "address_proof"
    OTHER = "other"


class ApplicationStatus(str, Enum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    ANALYZING_ORIGIN = "analyzing_origin"
    ANALYZED = "analyzed"
    IN_RING = "in_ring"
    CLEARED = "cleared"
    FAILED = "failed"


class ApplicationCreate(BaseModel):
    """Payload to register a new application (before any analysis runs)."""

    applicant_name: str = Field(..., min_length=1, max_length=200)
    pan: str | None = Field(None, pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$")
    phone: str | None = Field(None, pattern=r"^\+?[0-9 \-]{7,20}$")
    email: str | None = Field(None, max_length=200)
    bank_account: str | None = Field(None, max_length=30)
    ifsc: str | None = Field(None, pattern=r"^[A-Z]{4}0[A-Z0-9]{6}$")
    city: str = Field(..., min_length=1, max_length=100)
    loan_amount_inr: int = Field(..., gt=0)
    purpose_of_loan: str | None = Field(None, max_length=500)
    employer_description: str | None = Field(None, max_length=500)
    address_line_2: str | None = Field(None, max_length=200)
    guarantor_name: str | None = Field(None, max_length=200)
    valuer_name: str | None = Field(None, max_length=200)
    submission_time: datetime


class Application(ApplicationCreate):
    """An application with system-assigned id, status, and timestamps."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    status: ApplicationStatus = ApplicationStatus.UPLOADED
    fraud_score: float | None = Field(None, ge=0.0, le=1.0)
    ring_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
