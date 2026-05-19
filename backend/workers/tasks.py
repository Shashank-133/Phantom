"""Celery tasks — the actual analysis pipeline run inside worker processes.

Two task entry points:

  analyze_application(application_id)
      Per-document forensics. Loads PDF bytes → pdf_parser → entropy →
      ViT → origin_engine → saves OriginCertificate. Publishes
      DOCUMENT_ANALYZED on completion.

  run_demo_analysis(batch_id)
      The hero task triggered by POST /analyze/demo. Runs analyze_application
      for all seeded applications, then builds the Neo4j graph, runs Louvain,
      scores each suspicious cluster, persists + signs reports, and publishes
      BATCH_COMPLETE with the full graph data.

Each task wraps async logic with asyncio.run() so the pipeline stays clean
(database calls are async) while the Celery surface stays synchronous.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from uuid import UUID

from celery import shared_task
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from config import get_settings
from database.models import ApplicationORM, DocumentORM, OriginCertificateORM, PhantomReportORM
from database.neo4j_client import Neo4jClient
from database.postgres import get_session_factory
from schemas.application import ApplicationStatus
from schemas.phantom_report import RecommendedAction
from services.community_detection import detect_communities
from services.cross_signal_engine import (
    PHANTOM_CONFIRMED_RING,
    PHANTOM_SUSPECTED_RING,
    score_cluster,
)
from services.graph_builder import build_graph
from services.origin_engine import score_document
from services.pdf_parser import parse_pdf
from services.pii_signals import fingerprint as pii_fingerprint
from services.report_generator import generate_report
from services.text_similarity import compute_embeddings
from workers.celery_app import celery_app  # noqa: F401 — ensures Celery picks this module up
from workers.events import publish_event


# ---------------------------------------------------------------------------
# Per-application analysis
# ---------------------------------------------------------------------------


async def _analyze_one(application_id: UUID, *, progress_label: str | None = None) -> dict:
    """Run pdf_parser → entropy → ViT → origin_engine for one application.

    Saves OriginCertificate to Postgres. Returns a small dict for the
    WebSocket event payload.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        # Load app + first document
        stmt = (
            select(ApplicationORM)
            .where(ApplicationORM.id == application_id)
            .options(selectinload(ApplicationORM.documents))
        )
        result = await session.execute(stmt)
        app = result.scalar_one_or_none()
        if app is None:
            raise ValueError(f"Application {application_id} not found")
        if not app.documents:
            raise ValueError(f"Application {application_id} has no documents")

        doc = app.documents[0]
        raw_bytes = bytes(doc.raw_bytes)

        # Mark in-progress
        app.status = ApplicationStatus.ANALYZING_ORIGIN.value
        await session.commit()

        # Run the pipeline (this is the slow part — ViT inference + parsing)
        parsed = parse_pdf(raw_bytes)
        cert = score_document(parsed, application_id=application_id, doc_id=doc.id)

        # Persist the certificate. ORM upsert pattern: delete-then-insert in
        # case we re-analyze. The unique constraint on document_id is the
        # cleanest way to enforce one-cert-per-doc.
        from sqlalchemy import delete

        await session.execute(
            delete(OriginCertificateORM).where(OriginCertificateORM.document_id == doc.id)
        )

        orm_cert = OriginCertificateORM(
            id=cert.doc_id,
            document_id=doc.id,
            application_id=app.id,
            cbs_match_score=cert.cbs_match_score,
            origin_tool=cert.origin_tool,
            tool_category=cert.tool_category.value,
            confidence=cert.confidence,
            font_subset_hash=cert.font_subset_hash,
            perceptual_hash=cert.perceptual_hash,
            entropy_profile=cert.entropy_profile.model_dump(),
            pdf_metadata=cert.pdf_metadata.model_dump(mode="json"),
            vit_embedding=cert.vit_embedding,
            creation_timestamp=cert.creation_timestamp,
        )
        session.add(orm_cert)
        app.status = ApplicationStatus.ANALYZED.value
        await session.commit()

    payload = {
        "application_id": str(application_id),
        "applicant_name": app.applicant_name,
        "cbs_match_score": cert.cbs_match_score,
        "origin_tool": cert.origin_tool,
        "tool_category": cert.tool_category.value,
        "confidence": cert.confidence,
        "font_subset_hash": cert.font_subset_hash,
    }
    if progress_label:
        payload["progress"] = progress_label

    publish_event("DOCUMENT_ANALYZED", **payload)
    return payload


@shared_task(name="phantom.analyze_application", bind=True)
def analyze_application(self, application_id: str) -> dict:
    """Celery entry point for analyzing a single application."""
    app_id = UUID(application_id)
    logger.info("analyze_application | id={}", application_id)
    try:
        return asyncio.run(_analyze_one(app_id))
    except Exception as e:
        logger.exception("analyze_application failed | id={}: {}", application_id, e)
        publish_event("ERROR", application_id=application_id, message=str(e))
        raise


# ---------------------------------------------------------------------------
# Full-batch (demo) analysis
# ---------------------------------------------------------------------------


async def _list_application_ids() -> list[UUID]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = select(ApplicationORM.id).order_by(ApplicationORM.submission_time)
        result = await session.execute(stmt)
        return [row[0] for row in result.all()]


async def _load_applications_and_certs() -> tuple[dict, dict]:
    """Return (applicants_by_id, certificates_by_app) — fully populated."""
    from schemas.origin_certificate import (
        EntropyProfile,
        OriginCertificate,
        PDFMetadata,
        ToolCategory,
    )

    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = (
            select(ApplicationORM)
            .options(
                selectinload(ApplicationORM.documents).selectinload(
                    DocumentORM.origin_certificate
                )
            )
            .order_by(ApplicationORM.submission_time)
        )
        result = await session.execute(stmt)
        apps = result.scalars().all()

    applicants_by_id: dict = {}
    certs_by_app: dict = {}

    for app in apps:
        applicants_by_id[app.id] = {
            "id": app.id,
            "application_id": app.id,
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
            "submission_time": app.submission_time,
        }

        if app.documents and app.documents[0].origin_certificate:
            orm_cert = app.documents[0].origin_certificate
            certs_by_app[app.id] = OriginCertificate(
                doc_id=orm_cert.id,
                application_id=app.id,
                cbs_match_score=orm_cert.cbs_match_score,
                origin_tool=orm_cert.origin_tool,
                tool_category=ToolCategory(orm_cert.tool_category),
                confidence=orm_cert.confidence,
                font_subset_hash=orm_cert.font_subset_hash,
                entropy_profile=EntropyProfile(**orm_cert.entropy_profile),
                perceptual_hash=orm_cert.perceptual_hash,
                vit_embedding=orm_cert.vit_embedding,
                pdf_metadata=PDFMetadata(**orm_cert.pdf_metadata),
                creation_timestamp=orm_cert.creation_timestamp,
            )

    return applicants_by_id, certs_by_app


async def _persist_report(report) -> None:
    """Upsert a PhantomReport row keyed by ring_id."""
    from sqlalchemy import delete

    session_factory = get_session_factory()
    async with session_factory() as session:
        await session.execute(
            delete(PhantomReportORM).where(PhantomReportORM.ring_id == report.ring_id)
        )
        session.add(
            PhantomReportORM(
                ring_id=report.ring_id,
                ring_size=report.ring_size,
                total_exposure_inr=report.total_exposure_inr,
                phantom_confidence_pct=report.phantom_confidence_pct,
                evidence_bundle=report.evidence_bundle.model_dump(mode="json"),
                evidence_hash_sha256=report.evidence_hash_sha256,
                evidence_signature_ed25519=report.evidence_signature_ed25519,
                signing_key_id=report.signing_key_id,
                origin_summary=report.origin_summary,
                timing_summary=report.timing_summary,
                narrative=report.narrative,
                recommended_action=report.recommended_action.value,
            )
        )
        await session.commit()


async def _tag_ring_members(ring_id: str, member_ids: list[UUID]) -> None:
    """Stamp ring_id + 'in_ring' status onto the participant applications."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = select(ApplicationORM).where(ApplicationORM.id.in_(member_ids))
        rows = (await session.execute(stmt)).scalars().all()
        for app in rows:
            app.ring_id = ring_id
            app.status = ApplicationStatus.IN_RING.value
        await session.commit()


async def _serialize_graph_for_frontend(neo4j: Neo4jClient, ring_members: set[str]) -> dict:
    """Build a D3-friendly graph payload."""
    node_rows = await neo4j.run(
        "MATCH (a:Application) "
        "RETURN a.id AS id, a.applicant_name AS name, a.city AS city, "
        "a.loan_amount_inr AS amount, a.origin_tool AS tool, "
        "a.cbs_match_score AS cbs_match_score, a.submission_time AS submission_time"
    )
    nodes = [
        {
            "id": row["id"],
            "name": row.get("name"),
            "city": row.get("city"),
            "amount": row.get("amount"),
            "origin_tool": row.get("tool"),
            "cbs_match_score": row.get("cbs_match_score"),
            "submission_time": str(row.get("submission_time")) if row.get("submission_time") else None,
            "in_ring": row["id"] in ring_members,
        }
        for row in node_rows
    ]

    from services.graph_builder import EDGE_WEIGHTS

    edges: list[dict] = []
    for rel in EDGE_WEIGHTS:
        rows = await neo4j.run(
            f"MATCH (a:Application)-[r:{rel}]->(b:Application) "
            f"RETURN a.id AS source, b.id AS target, r.weight AS weight"
        )
        for row in rows:
            edges.append(
                {
                    "source": row["source"],
                    "target": row["target"],
                    "type": rel,
                    "weight": row.get("weight") or EDGE_WEIGHTS[rel],
                }
            )

    return {"nodes": nodes, "links": edges}


async def _run_demo(batch_id: str) -> dict:
    """Full pipeline: per-doc analysis → graph → Louvain → score → report → WS."""
    settings = get_settings()  # noqa: F841 — keeps env initialized for ML imports
    neo4j = Neo4jClient()

    try:
        application_ids = await _list_application_ids()
        total = len(application_ids)
        if total == 0:
            publish_event("ERROR", message="No applications in database — seed first")
            return {"status": "no_applications"}

        publish_event("ANALYSIS_STARTED", batch_id=batch_id, total=total)

        # ---- Per-document forensics ----
        for i, app_id in enumerate(application_ids, start=1):
            try:
                await _analyze_one(app_id, progress_label=f"{i}/{total}")
            except Exception as e:
                logger.exception("Per-doc analysis failed | app={}: {}", app_id, e)
                publish_event("ERROR", application_id=str(app_id), message=str(e))

        # ---- Cross-applicant graph ----
        session_factory = get_session_factory()
        async with session_factory() as session:
            graph_summary = await build_graph(session, neo4j)

        publish_event(
            "GRAPH_BUILT",
            nodes=graph_summary.nodes_upserted,
            total_edges=graph_summary.total_edges,
            edges_by_type=graph_summary.edges_by_type,
        )

        # ---- Community detection ----
        detection = await detect_communities(neo4j)
        publish_event(
            "COMMUNITIES_DETECTED",
            communities=len(set(detection.partitions.values())),
            suspicious=len(detection.suspicious_clusters),
        )

        # ---- Score each suspicious cluster ----
        applicants_by_id, certs_by_app = await _load_applications_and_certs()
        text_embeddings = compute_embeddings(list(applicants_by_id.values()))
        pii_fps = {aid: pii_fingerprint(app) for aid, app in applicants_by_id.items()}

        ring_member_ids: set[str] = set()
        reports = []

        for cluster in detection.suspicious_clusters:
            verdict = score_cluster(
                cluster.member_ids,
                applicants_by_id=applicants_by_id,
                certificates_by_app=certs_by_app,
                embeddings_by_app=text_embeddings,
                pii_fingerprints_by_app=pii_fps,
            )

            if verdict.recommended_action == RecommendedAction.CLEAR:
                # Don't bother building a report for clusters that score below
                # the suspected-ring threshold (PHANTOM_SUSPECTED_RING).
                continue

            report = generate_report(
                verdict,
                applicants_by_id=applicants_by_id,
                certificates_by_app=certs_by_app,
            )
            await _persist_report(report)
            await _tag_ring_members(report.ring_id, verdict.member_ids)

            for mid in verdict.member_ids:
                ring_member_ids.add(str(mid))

            report_payload = report.model_dump(mode="json")
            reports.append(report_payload)

            publish_event(
                "RING_DETECTED",
                ring_id=report.ring_id,
                ring_size=report.ring_size,
                phantom_score=report.phantom_confidence_pct / 100.0,
                phantom_confidence_pct=report.phantom_confidence_pct,
                total_exposure_inr=report.total_exposure_inr,
                recommended_action=report.recommended_action.value,
                report=report_payload,
            )

        # ---- Final frontend payload ----
        graph_data = await _serialize_graph_for_frontend(neo4j, ring_member_ids)

        publish_event(
            "BATCH_COMPLETE",
            batch_id=batch_id,
            ring_count=len(reports),
            rings=reports,
            graph_data=graph_data,
        )

        logger.info(
            "Demo batch complete | batch={} | rings={} | flagged_members={}",
            batch_id, len(reports), len(ring_member_ids),
        )

        return {
            "batch_id": batch_id,
            "status": "complete",
            "ring_count": len(reports),
            "flagged_member_ids": list(ring_member_ids),
        }

    finally:
        await neo4j.close()


@shared_task(name="phantom.run_demo_analysis", bind=True)
def run_demo_analysis(self, batch_id: str | None = None) -> dict:
    """Celery entry point for POST /analyze/demo."""
    batch_id = batch_id or f"BATCH-{uuid.uuid4().hex[:12]}"
    logger.info("run_demo_analysis | batch={}", batch_id)
    try:
        return asyncio.run(_run_demo(batch_id))
    except Exception as e:
        logger.exception("run_demo_analysis failed | batch={}: {}", batch_id, e)
        publish_event("ERROR", batch_id=batch_id, message=str(e))
        raise
