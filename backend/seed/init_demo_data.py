"""Demo-data seeder — populates Postgres + Neo4j from demo_data/applications_index.json.

Idempotent — only seeds when the `applications` table is empty. Called by
backend/main.py's FastAPI lifespan on every startup, so the demo is ready the
moment the backend comes online.

If the index file is missing (i.e. generate_demo.py hasn't been run yet), the
seeder logs a clear warning and returns False without crashing. The Demo Mode
button on the frontend can later re-trigger seeding via an API endpoint that
calls demo_data.generate_demo.generate() first.

Prerequisites for full seeding:
    1. python demo_data/generate_demo.py   (creates the 40 PDFs + index)
    2. Postgres + Neo4j running
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ApplicationORM, DocumentORM
from database.neo4j_client import Neo4jClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEMO_INDEX_FILE = PROJECT_ROOT / "demo_data" / "applications_index.json"


async def _is_empty(session: AsyncSession) -> bool:
    result = await session.execute(select(func.count()).select_from(ApplicationORM))
    count = result.scalar_one()
    return count == 0


def _load_index() -> dict | None:
    if not DEMO_INDEX_FILE.exists():
        logger.warning(
            "Demo index file not found at {}. "
            "Run `python demo_data/generate_demo.py` to create it.",
            DEMO_INDEX_FILE,
        )
        return None
    try:
        return json.loads(DEMO_INDEX_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Failed to parse demo index: {}", e)
        return None


async def _seed_postgres(session: AsyncSession, entries: list[dict]) -> int:
    """Insert applications + their documents. Returns count of apps inserted."""
    inserted = 0
    for entry in entries:
        pdf_path = PROJECT_ROOT / entry["pdf_path"]
        if not pdf_path.exists():
            logger.warning("PDF missing on disk, skipping: {}", pdf_path)
            continue

        pdf_bytes = pdf_path.read_bytes()

        app = ApplicationORM(
            id=UUID(entry["application_id"]),
            applicant_name=entry["applicant_name"],
            pan=entry.get("pan"),
            phone=entry.get("phone"),
            email=entry.get("email"),
            bank_account=entry.get("bank_account"),
            ifsc=entry.get("ifsc"),
            city=entry["city"],
            loan_amount_inr=int(entry["loan_amount_inr"]),
            purpose_of_loan=entry.get("purpose_of_loan"),
            employer_description=entry.get("employer_description"),
            address_line_2=entry.get("address_line_2"),
            guarantor_name=entry.get("guarantor_name"),
            valuer_name=entry.get("valuer_name"),
            submission_time=datetime.fromisoformat(entry["submission_time"]),
            status="uploaded",
        )
        session.add(app)

        doc = DocumentORM(
            id=UUID(entry["document_id"]),
            application_id=app.id,
            document_type="salary_slip",
            filename=entry["pdf_filename"],
            raw_bytes=pdf_bytes,
            file_size_bytes=entry["file_size_bytes"],
            status="uploaded",
        )
        session.add(doc)

        inserted += 1

    await session.commit()
    return inserted


async def _seed_neo4j(neo4j: Neo4jClient, entries: list[dict]) -> int:
    """Insert Application nodes (no edges yet — Day 4's graph_builder adds those)."""
    query = """
    MERGE (a:Application {id: $id})
    SET a.applicant_name = $applicant_name,
        a.city = $city,
        a.loan_amount_inr = $loan_amount_inr,
        a.submission_time = datetime($submission_time),
        a.phone = $phone,
        a.email = $email,
        a.bank_account = $bank_account,
        a.ifsc = $ifsc,
        a.guarantor_name = $guarantor_name,
        a.valuer_name = $valuer_name,
        a.status = 'uploaded'
    """

    batch = [
        {
            "id": entry["application_id"],
            "applicant_name": entry["applicant_name"],
            "city": entry["city"],
            "loan_amount_inr": int(entry["loan_amount_inr"]),
            "submission_time": entry["submission_time"],
            "phone": entry.get("phone"),
            "email": entry.get("email"),
            "bank_account": entry.get("bank_account"),
            "ifsc": entry.get("ifsc"),
            "guarantor_name": entry.get("guarantor_name"),
            "valuer_name": entry.get("valuer_name"),
        }
        for entry in entries
    ]

    await neo4j.batch_write(query, batch)
    return len(batch)


async def seed_if_empty(session: AsyncSession, neo4j: Neo4jClient) -> bool:
    """Populate Postgres + Neo4j with the 40 demo applications if DB is empty.

    Returns True if seeding occurred, False if DB was already populated or
    the demo index is missing.
    """
    if not await _is_empty(session):
        logger.info("applications table not empty — skipping demo seed")
        return False

    index = _load_index()
    if index is None:
        return False

    entries = index.get("entries", [])
    if not entries:
        logger.warning("Demo index has no entries")
        return False

    logger.info("Seeding demo data | {} applications", len(entries))

    try:
        pg_count = await _seed_postgres(session, entries)
        neo_count = await _seed_neo4j(neo4j, entries)
    except Exception as e:
        logger.exception("Demo seeding failed: {}", e)
        await session.rollback()
        return False

    logger.info(
        "Demo seed complete | postgres={} | neo4j={}",
        pg_count,
        neo_count,
    )
    return True


async def reseed_force(session: AsyncSession, neo4j: Neo4jClient) -> bool:
    """Wipe + reseed. Used by the /analyze/demo endpoint if user wants a fresh run."""
    from sqlalchemy import delete

    logger.warning("Force-reseeding demo data (wiping existing rows)")
    await session.execute(delete(ApplicationORM))
    await session.commit()
    await neo4j.clear_graph()

    index = _load_index()
    if index is None:
        return False

    entries = index.get("entries", [])
    await _seed_postgres(session, entries)
    await _seed_neo4j(neo4j, entries)
    logger.info("Force-reseed complete")
    return True
