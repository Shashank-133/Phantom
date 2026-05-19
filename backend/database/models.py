"""SQLAlchemy ORM models — the Postgres persistence layer.

Mirrors the Pydantic schemas in backend/schemas/ but adds DB concerns:
primary keys, foreign keys, indexes, timestamps, JSONB columns for nested
data, and the audit trail columns (created_at, updated_at).

Tables:
  applications          — 40 demo rows + any uploaded
  documents             — PDF blobs, one or more per application
  origin_certificates   — forensic verdict per document
  phantom_reports       — confirmed fraud rings (Ed25519-signed bundles)

Imported lazily by database.postgres.create_tables() so that importing
database.postgres alone doesn't pull in SQLAlchemy ORM machinery on hot paths.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.postgres import Base


class ApplicationORM(Base):
    __tablename__ = "applications"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    applicant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    pan: Mapped[str | None] = mapped_column(String(10))
    phone: Mapped[str | None] = mapped_column(String(20), index=True)
    email: Mapped[str | None] = mapped_column(String(200))
    bank_account: Mapped[str | None] = mapped_column(String(30), index=True)
    ifsc: Mapped[str | None] = mapped_column(String(11), index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    loan_amount_inr: Mapped[int] = mapped_column(BigInteger, nullable=False)

    purpose_of_loan: Mapped[str | None] = mapped_column(Text)
    employer_description: Mapped[str | None] = mapped_column(Text)
    address_line_2: Mapped[str | None] = mapped_column(Text)
    guarantor_name: Mapped[str | None] = mapped_column(String(200), index=True)
    valuer_name: Mapped[str | None] = mapped_column(String(200), index=True)

    submission_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="uploaded", index=True)
    fraud_score: Mapped[float | None] = mapped_column(Float)
    ring_id: Mapped[str | None] = mapped_column(String(64), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    documents: Mapped[list["DocumentORM"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_apps_submission_status", "submission_time", "status"),
    )


class DocumentORM(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type: Mapped[str] = mapped_column(String(40), nullable=False, default="salary_slip")
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    application: Mapped[ApplicationORM] = relationship(back_populates="documents")
    origin_certificate: Mapped["OriginCertificateORM | None"] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )


class OriginCertificateORM(Base):
    __tablename__ = "origin_certificates"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    application_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    cbs_match_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    origin_tool: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tool_category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    font_subset_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    perceptual_hash: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # Nested data as JSONB — queryable, but mostly read back as a blob.
    entropy_profile: Mapped[dict] = mapped_column(JSONB, nullable=False)
    pdf_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False)
    vit_embedding: Mapped[list[float] | None] = mapped_column(JSONB)

    creation_timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    document: Mapped[DocumentORM] = relationship(back_populates="origin_certificate")


class PhantomReportORM(Base):
    __tablename__ = "phantom_reports"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    ring_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    ring_size: Mapped[int] = mapped_column(Integer, nullable=False)
    total_exposure_inr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    phantom_confidence_pct: Mapped[float] = mapped_column(Float, nullable=False, index=True)

    evidence_bundle: Mapped[dict] = mapped_column(JSONB, nullable=False)
    evidence_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_signature_ed25519: Mapped[str] = mapped_column(Text, nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String(32), nullable=False)

    origin_summary: Mapped[str] = mapped_column(Text, nullable=False)
    timing_summary: Mapped[str] = mapped_column(Text, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(40), nullable=False)

    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
