"""Evidence routes — download the signed PHANTOM evidence bundle + verify signatures.

Three endpoints:
  GET /evidence/public-key       — Ed25519 public key in PEM (anyone can verify)
  GET /evidence/{ring_id}.pdf    — court-ready PDF rendering of the report
  GET /evidence/{ring_id}        — full Ed25519-signed evidence bundle JSON

The `.pdf` route is declared BEFORE the catch-all `{ring_id}` route on purpose:
FastAPI evaluates routes top-to-bottom and `{ring_id}` would otherwise swallow
"RING-XYZ.pdf" as a ring id rather than recognising the extension.
"""
from __future__ import annotations

from datetime import datetime

import orjson
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import db_session
from crypto.signer import get_signer
from database.models import PhantomReportORM
from schemas.phantom_report import PHANTOMReport
from services.pdf_report_builder import build_phantom_report_pdf

router = APIRouter(prefix="/evidence", tags=["evidence"])


def _orm_row_to_report(r: PhantomReportORM) -> PHANTOMReport:
    """Reconstruct the strongly-typed report object from the ORM row."""
    return PHANTOMReport.model_validate(
        {
            "ring_id": r.ring_id,
            "ring_size": r.ring_size,
            "total_exposure_inr": r.total_exposure_inr,
            "phantom_confidence_pct": r.phantom_confidence_pct,
            "evidence_bundle": r.evidence_bundle,
            "evidence_hash_sha256": r.evidence_hash_sha256,
            "evidence_signature_ed25519": r.evidence_signature_ed25519,
            "signing_key_id": r.signing_key_id,
            "origin_summary": r.origin_summary,
            "timing_summary": r.timing_summary,
            "narrative": r.narrative,
            "recommended_action": r.recommended_action,
            "generated_at": r.generated_at,
        }
    )


@router.get("/public-key")
async def public_key() -> dict:
    """Return the Ed25519 public key in PEM. Anyone can use this to verify a bundle."""
    signer = get_signer()
    return {
        "key_id": signer.key_id,
        "algorithm": "Ed25519",
        "public_key_pem": signer.public_key_pem,
    }


@router.get("/{ring_id}.pdf")
async def get_evidence_pdf(
    ring_id: str, session: AsyncSession = Depends(db_session)
) -> Response:
    """Render the PHANTOM Report as a polished PDF.

    The PDF carries the same signed evidence bundle (SHA-256 + Ed25519
    signature + key id are visible in the footer block); the JSON endpoint
    below remains canonical for programmatic verification.
    """
    stmt = select(PhantomReportORM).where(PhantomReportORM.ring_id == ring_id)
    r = (await session.execute(stmt)).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Ring not found")

    report = _orm_row_to_report(r)
    pdf_bytes = build_phantom_report_pdf(report)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="phantom-report-{ring_id}.pdf"',
        },
    )


@router.get("/{ring_id}")
async def get_evidence_bundle(
    ring_id: str, session: AsyncSession = Depends(db_session)
) -> Response:
    """Download the full signed evidence bundle for a confirmed ring.

    Response contents:
      evidence_bundle:               the bundle as a JSON object
      evidence_hash_sha256:          for quick eyeballing
      evidence_signature_ed25519:    base64
      signing_key_id:                short fingerprint
      verification_instructions:     human note explaining how to verify

    Bundle is served as application/json with a Content-Disposition that
    suggests "phantom-evidence-<ring_id>.json" to make Save-As DTRT.
    """
    stmt = select(PhantomReportORM).where(PhantomReportORM.ring_id == ring_id)
    r = (await session.execute(stmt)).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Ring not found")

    payload = {
        "ring_id": r.ring_id,
        "ring_size": r.ring_size,
        "total_exposure_inr": r.total_exposure_inr,
        "phantom_confidence_pct": r.phantom_confidence_pct,
        "recommended_action": r.recommended_action,
        "origin_summary": r.origin_summary,
        "timing_summary": r.timing_summary,
        "narrative": r.narrative,
        "evidence_bundle": r.evidence_bundle,
        "evidence_hash_sha256": r.evidence_hash_sha256,
        "evidence_signature_ed25519": r.evidence_signature_ed25519,
        "signing_key_id": r.signing_key_id,
        "generated_at": r.generated_at.isoformat(),
        "downloaded_at": datetime.utcnow().isoformat(),
        "verification_instructions": (
            "Canonical-JSON encode `evidence_bundle` (sort_keys=True, "
            "separators=(',', ':'), default=isoformat for datetimes/UUIDs). "
            "Verify Ed25519 signature using the public key at "
            "/evidence/public-key (key_id must match)."
        ),
    }

    body = orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="phantom-evidence-{ring_id}.json"',
        },
    )
