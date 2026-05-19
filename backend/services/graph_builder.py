"""Graph builder — turns the 40 applications + their certificates into a
Neo4j cross-applicant knowledge graph.

Reads from Postgres (applications + their origin_certificates), writes to
Neo4j (Application nodes + 7 edge types). Idempotent — re-running it after
new data lands is safe.

Edge types and their triggers:

  TEMPLATE_MATCH        same font_subset_hash OR perceptual-hash Hamming < 10
  TIMING_PROXIMITY      |submission_a - submission_b| < 10 minutes
  SAME_GUARANTOR        same normalized guarantor_name
  SAME_VALUER           same normalized valuer_name
  SHARED_PII            pii_signals.is_shared_pii (Upgrade A)
  TEXT_MATCH            text_similarity.is_text_match (Upgrade A)
  NAME_SIMILARITY       name_match.is_name_similar  (Upgrade A)

Each edge type carries a `weight` property so Louvain (Day 4 next step) can
treat strong evidence (template match) more heavily than weak hints (timing).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import imagehash
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import ApplicationORM, DocumentORM, OriginCertificateORM
from database.neo4j_client import Neo4jClient
from services.name_match import is_name_similar, normalize_name
from services.pii_signals import fingerprint as pii_fingerprint, is_shared_pii
from services.text_similarity import compute_embeddings, is_text_match

# Edge configuration — (cypher_relation, weight)
EDGE_WEIGHTS = {
    "TEMPLATE_MATCH": 1.0,
    "TIMING_PROXIMITY": 0.4,
    "SAME_GUARANTOR": 0.7,
    "SAME_VALUER": 0.7,
    "SHARED_PII": 0.6,
    "TEXT_MATCH": 0.8,
    "NAME_SIMILARITY": 0.5,
}

TIMING_WINDOW = timedelta(minutes=10)
PHASH_HAMMING_THRESHOLD = 10  # ≤ this counts as a template match


@dataclass
class ApplicationBundle:
    """All data we need about one application to compute pairwise edges."""

    id: UUID
    applicant_name: str
    city: str
    loan_amount_inr: int
    submission_time: datetime
    guarantor_name_norm: str
    valuer_name_norm: str
    pii_fp: object  # PIIFingerprint, kept as Any to avoid leaking pii_signals types
    font_subset_hash: str | None
    perceptual_hash: str | None
    cbs_match_score: float | None
    origin_tool: str | None
    raw_dict: dict  # echoed for text_similarity + report assembly


def _phash_from_hex(h: str | None):
    """Convert the stored hex perceptual hash back to an imagehash object."""
    if not h:
        return None
    try:
        return imagehash.hex_to_hash(h)
    except (ValueError, TypeError):
        return None


def _is_template_match(a: ApplicationBundle, b: ApplicationBundle) -> bool:
    if a.font_subset_hash and a.font_subset_hash == b.font_subset_hash:
        return True
    pa = _phash_from_hex(a.perceptual_hash)
    pb = _phash_from_hex(b.perceptual_hash)
    if pa is None or pb is None:
        return False
    return (pa - pb) < PHASH_HAMMING_THRESHOLD


def _is_timing_proximate(a: ApplicationBundle, b: ApplicationBundle) -> bool:
    return abs((a.submission_time - b.submission_time).total_seconds()) < TIMING_WINDOW.total_seconds()


def _same_normalized_attr(a: str, b: str) -> bool:
    return bool(a) and bool(b) and a == b


async def _load_bundles(session: AsyncSession) -> list[ApplicationBundle]:
    """Fetch all applications + their first document's origin certificate."""
    stmt = (
        select(ApplicationORM)
        .options(
            selectinload(ApplicationORM.documents).selectinload(DocumentORM.origin_certificate)
        )
        .order_by(ApplicationORM.submission_time)
    )
    result = await session.execute(stmt)
    apps = result.scalars().all()

    bundles: list[ApplicationBundle] = []
    for app in apps:
        cert: OriginCertificateORM | None = None
        if app.documents:
            cert = app.documents[0].origin_certificate

        raw = {
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

        bundles.append(
            ApplicationBundle(
                id=app.id,
                applicant_name=app.applicant_name,
                city=app.city,
                loan_amount_inr=app.loan_amount_inr,
                submission_time=app.submission_time,
                guarantor_name_norm=normalize_name(app.guarantor_name),
                valuer_name_norm=normalize_name(app.valuer_name),
                pii_fp=pii_fingerprint(raw),
                font_subset_hash=cert.font_subset_hash if cert else None,
                perceptual_hash=cert.perceptual_hash if cert else None,
                cbs_match_score=cert.cbs_match_score if cert else None,
                origin_tool=cert.origin_tool if cert else None,
                raw_dict=raw,
            )
        )

    return bundles


async def _upsert_application_nodes(neo4j: Neo4jClient, bundles: list[ApplicationBundle]) -> None:
    """Refresh Application node properties from latest origin-cert data."""
    query = """
    MERGE (a:Application {id: $id})
    SET a.applicant_name = $applicant_name,
        a.city = $city,
        a.loan_amount_inr = $loan_amount,
        a.submission_time = datetime($submission_time),
        a.font_subset_hash = $font_subset_hash,
        a.origin_tool = $origin_tool,
        a.cbs_match_score = $cbs_match_score
    """
    batch = [
        {
            "id": str(b.id),
            "applicant_name": b.applicant_name,
            "city": b.city,
            "loan_amount": b.loan_amount_inr,
            "submission_time": b.submission_time.isoformat(),
            "font_subset_hash": b.font_subset_hash,
            "origin_tool": b.origin_tool,
            "cbs_match_score": b.cbs_match_score,
        }
        for b in bundles
    ]
    await neo4j.batch_write(query, batch)


async def _clear_existing_edges(neo4j: Neo4jClient) -> None:
    """Drop all the analytical edge types before recomputing.

    Application nodes are preserved. Only the analysis edges go.
    """
    for rel in EDGE_WEIGHTS.keys():
        await neo4j.run(f"MATCH ()-[r:{rel}]->() DELETE r")


async def _write_edges(
    neo4j: Neo4jClient,
    rel_type: str,
    edges: list[tuple[UUID, UUID, float]],
) -> None:
    """Write one batch of edges of a given relationship type, with per-edge weight."""
    if not edges:
        return

    query = (
        f"MATCH (a:Application {{id: $a}}), (b:Application {{id: $b}}) "
        f"MERGE (a)-[r:{rel_type}]->(b) "
        f"SET r.weight = $weight"
    )

    batch = [{"a": str(a), "b": str(b), "weight": w} for a, b, w in edges]
    await neo4j.batch_write(query, batch)


@dataclass
class GraphBuildSummary:
    nodes_upserted: int
    edges_by_type: dict[str, int]
    total_edges: int

    def as_dict(self) -> dict:
        return {
            "nodes_upserted": self.nodes_upserted,
            "edges_by_type": self.edges_by_type,
            "total_edges": self.total_edges,
        }


async def build_graph(
    session: AsyncSession,
    neo4j: Neo4jClient,
    *,
    clear_existing: bool = True,
) -> GraphBuildSummary:
    """End-to-end: read Postgres, compute pairwise edges, write Neo4j."""
    bundles = await _load_bundles(session)
    if not bundles:
        logger.warning("No applications found — graph build is a no-op")
        return GraphBuildSummary(0, {}, 0)

    logger.info("Graph build | {} applications", len(bundles))

    # Refresh node properties (origin-cert data may be newer than seed).
    await _upsert_application_nodes(neo4j, bundles)
    if clear_existing:
        await _clear_existing_edges(neo4j)

    # Pre-compute the text-similarity embeddings ONCE (batched encode).
    text_embeddings = compute_embeddings([b.raw_dict for b in bundles])
    text_enabled = text_embeddings is not None
    if not text_enabled:
        logger.warning("Text embeddings unavailable — TEXT_MATCH edges skipped")

    # Collect edges by type so we batch-write each set in one transaction.
    edges: dict[str, list[tuple[UUID, UUID, float]]] = {k: [] for k in EDGE_WEIGHTS}

    n = len(bundles)
    for i in range(n):
        a = bundles[i]
        for j in range(i + 1, n):
            b = bundles[j]

            if _is_template_match(a, b):
                edges["TEMPLATE_MATCH"].append((a.id, b.id, EDGE_WEIGHTS["TEMPLATE_MATCH"]))
            if _is_timing_proximate(a, b):
                edges["TIMING_PROXIMITY"].append((a.id, b.id, EDGE_WEIGHTS["TIMING_PROXIMITY"]))
            if _same_normalized_attr(a.guarantor_name_norm, b.guarantor_name_norm):
                edges["SAME_GUARANTOR"].append((a.id, b.id, EDGE_WEIGHTS["SAME_GUARANTOR"]))
            if _same_normalized_attr(a.valuer_name_norm, b.valuer_name_norm):
                edges["SAME_VALUER"].append((a.id, b.id, EDGE_WEIGHTS["SAME_VALUER"]))
            if is_shared_pii(a.pii_fp, b.pii_fp):
                edges["SHARED_PII"].append((a.id, b.id, EDGE_WEIGHTS["SHARED_PII"]))
            if is_name_similar(a.applicant_name, b.applicant_name):
                edges["NAME_SIMILARITY"].append((a.id, b.id, EDGE_WEIGHTS["NAME_SIMILARITY"]))
            if text_enabled and is_text_match(text_embeddings, a.id, b.id):
                edges["TEXT_MATCH"].append((a.id, b.id, EDGE_WEIGHTS["TEXT_MATCH"]))

    edges_by_type: dict[str, int] = {}
    for rel, e_list in edges.items():
        await _write_edges(neo4j, rel, e_list)
        edges_by_type[rel] = len(e_list)

    total = sum(edges_by_type.values())
    summary = GraphBuildSummary(
        nodes_upserted=len(bundles),
        edges_by_type=edges_by_type,
        total_edges=total,
    )

    logger.info(
        "Graph build complete | nodes={} | edges={} | breakdown={}",
        summary.nodes_upserted,
        summary.total_edges,
        summary.edges_by_type,
    )
    return summary
