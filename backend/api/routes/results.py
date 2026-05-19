"""Read-side routes — applications, reports, graph data.

Everything here is for the frontend to fetch current state on page load
(after that, WebSocket events keep the UI live).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.deps import db_session, neo4j_client
from database.models import (
    ApplicationORM,
    DocumentORM,
    OriginCertificateORM,
    PhantomReportORM,
)
from database.neo4j_client import Neo4jClient
from services.graph_builder import EDGE_WEIGHTS

router = APIRouter(tags=["results"])


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------


@router.get("/applications")
async def list_applications(session: AsyncSession = Depends(db_session)) -> list[dict]:
    stmt = (
        select(ApplicationORM)
        .options(
            selectinload(ApplicationORM.documents).selectinload(
                DocumentORM.origin_certificate
            )
        )
        .order_by(ApplicationORM.submission_time)
    )
    rows = (await session.execute(stmt)).scalars().all()

    out: list[dict] = []
    for app in rows:
        cert = app.documents[0].origin_certificate if app.documents else None
        out.append(
            {
                "id": str(app.id),
                "applicant_name": app.applicant_name,
                "city": app.city,
                "loan_amount_inr": app.loan_amount_inr,
                "submission_time": app.submission_time.isoformat(),
                "status": app.status,
                "ring_id": app.ring_id,
                "fraud_score": app.fraud_score,
                "origin_tool": cert.origin_tool if cert else None,
                "tool_category": cert.tool_category if cert else None,
                "cbs_match_score": cert.cbs_match_score if cert else None,
                "confidence": cert.confidence if cert else None,
            }
        )
    return out


@router.get("/applications/{application_id}")
async def get_application(
    application_id: UUID, session: AsyncSession = Depends(db_session)
) -> dict:
    stmt = (
        select(ApplicationORM)
        .where(ApplicationORM.id == application_id)
        .options(
            selectinload(ApplicationORM.documents).selectinload(
                DocumentORM.origin_certificate
            )
        )
    )
    app = (await session.execute(stmt)).scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    cert = app.documents[0].origin_certificate if app.documents else None
    doc = app.documents[0] if app.documents else None

    return {
        "id": str(app.id),
        "applicant_name": app.applicant_name,
        "pan": app.pan,
        "phone": app.phone,
        "email": app.email,
        "bank_account": app.bank_account,
        "ifsc": app.ifsc,
        "city": app.city,
        "loan_amount_inr": app.loan_amount_inr,
        "purpose_of_loan": app.purpose_of_loan,
        "employer_description": app.employer_description,
        "address_line_2": app.address_line_2,
        "guarantor_name": app.guarantor_name,
        "valuer_name": app.valuer_name,
        "submission_time": app.submission_time.isoformat(),
        "status": app.status,
        "ring_id": app.ring_id,
        "fraud_score": app.fraud_score,
        "document": (
            {
                "id": str(doc.id),
                "filename": doc.filename,
                "file_size_bytes": doc.file_size_bytes,
                "document_type": doc.document_type,
            }
            if doc
            else None
        ),
        "origin_certificate": (
            {
                "id": str(cert.id),
                "cbs_match_score": cert.cbs_match_score,
                "origin_tool": cert.origin_tool,
                "tool_category": cert.tool_category,
                "confidence": cert.confidence,
                "font_subset_hash": cert.font_subset_hash,
                "perceptual_hash": cert.perceptual_hash,
                "entropy_profile": cert.entropy_profile,
                "pdf_metadata": cert.pdf_metadata,
                "creation_timestamp": (
                    cert.creation_timestamp.isoformat() if cert.creation_timestamp else None
                ),
            }
            if cert
            else None
        ),
    }


# ---------------------------------------------------------------------------
# PHANTOM Reports
# ---------------------------------------------------------------------------


@router.get("/reports")
async def list_reports(session: AsyncSession = Depends(db_session)) -> list[dict]:
    stmt = select(PhantomReportORM).order_by(PhantomReportORM.generated_at.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "ring_id": r.ring_id,
            "ring_size": r.ring_size,
            "total_exposure_inr": r.total_exposure_inr,
            "phantom_confidence_pct": r.phantom_confidence_pct,
            "recommended_action": r.recommended_action,
            "evidence_hash_sha256": r.evidence_hash_sha256,
            "signing_key_id": r.signing_key_id,
            "generated_at": r.generated_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/reports/{ring_id}")
async def get_report(ring_id: str, session: AsyncSession = Depends(db_session)) -> dict:
    stmt = select(PhantomReportORM).where(PhantomReportORM.ring_id == ring_id)
    r = (await session.execute(stmt)).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Report not found")

    return {
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
    }


# ---------------------------------------------------------------------------
# Graph data (for the D3 force-directed view)
# ---------------------------------------------------------------------------


@router.get("/graph")
async def get_graph(neo4j: Neo4jClient = Depends(neo4j_client)) -> dict:
    """Current Neo4j graph snapshot — D3 force-directed payload."""
    node_rows = await neo4j.run(
        "MATCH (a:Application) "
        "RETURN a.id AS id, a.applicant_name AS name, a.city AS city, "
        "a.loan_amount_inr AS amount, a.origin_tool AS tool, "
        "a.cbs_match_score AS cbs_match_score"
    )
    nodes = [
        {
            "id": row["id"],
            "name": row.get("name"),
            "city": row.get("city"),
            "amount": row.get("amount"),
            "origin_tool": row.get("tool"),
            "cbs_match_score": row.get("cbs_match_score"),
        }
        for row in node_rows
    ]

    links: list[dict] = []
    for rel in EDGE_WEIGHTS:
        rows = await neo4j.run(
            f"MATCH (a:Application)-[r:{rel}]->(b:Application) "
            f"RETURN a.id AS source, b.id AS target, r.weight AS weight"
        )
        for row in rows:
            links.append(
                {
                    "source": row["source"],
                    "target": row["target"],
                    "type": rel,
                    "weight": row.get("weight") or EDGE_WEIGHTS[rel],
                }
            )

    return {"nodes": nodes, "links": links, "node_count": len(nodes), "link_count": len(links)}
