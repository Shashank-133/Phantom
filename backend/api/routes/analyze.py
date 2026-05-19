"""Analysis routes — kick off the Celery pipeline.

Two endpoints:
  POST /analyze/demo     — run the full 40-application demo pipeline
  POST /analyze/batch    — analyze any pending applications (for uploaded data)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import db_session, neo4j_client
from api.ws_manager import get_ws_manager
from database.models import ApplicationORM
from database.neo4j_client import Neo4jClient
from seed.init_demo_data import reseed_force, seed_if_empty
from workers.events import publish_event
from workers.tasks import analyze_application, run_demo_analysis

router = APIRouter(prefix="/analyze", tags=["analyze"])


class DemoLaunch(BaseModel):
    batch_id: str
    job_id: str
    application_count: int
    seeded: bool
    started_at: datetime


@router.post("/demo", response_model=DemoLaunch, status_code=status.HTTP_202_ACCEPTED)
async def analyze_demo(
    reset: Annotated[bool, Query(description="Wipe + reseed before analysis")] = False,
    session: AsyncSession = Depends(db_session),
    neo4j: Neo4jClient = Depends(neo4j_client),
) -> DemoLaunch:
    """Run the cinematic-reveal pipeline against the pre-seeded 40 applications.

    Returns immediately with a job_id; progress arrives over the /ws channel.
    If `reset=true`, wipes the DB and reseeds first (useful for repeat demos).
    """
    seeded = False
    if reset:
        ok = await reseed_force(session, neo4j)
        if not ok:
            raise HTTPException(
                status_code=503,
                detail="Re-seed failed — is demo_data/applications_index.json present?",
            )
        seeded = True
    else:
        seeded = await seed_if_empty(session, neo4j)

    # Count what we're about to analyze
    count_stmt = select(ApplicationORM.id)
    count = len((await session.execute(count_stmt)).all())
    if count == 0:
        raise HTTPException(
            status_code=503,
            detail="No applications to analyze — run demo_data/generate_demo.py and reseed.",
        )

    batch_id = f"BATCH-{uuid.uuid4().hex[:12]}"
    async_result = run_demo_analysis.delay(batch_id)

    logger.info("Queued demo analysis | batch={} | celery_task={}", batch_id, async_result.id)

    # Make sure the browser hears about it even if it just connected.
    publish_event("DEMO_QUEUED", batch_id=batch_id, application_count=count)

    return DemoLaunch(
        batch_id=batch_id,
        job_id=async_result.id,
        application_count=count,
        seeded=seeded,
        started_at=datetime.utcnow(),
    )


class BatchAnalysisLaunch(BaseModel):
    batch_id: str
    queued: int


@router.post("/batch", response_model=BatchAnalysisLaunch, status_code=status.HTTP_202_ACCEPTED)
async def analyze_batch(
    session: AsyncSession = Depends(db_session),
) -> BatchAnalysisLaunch:
    """Queue analyze_application for every application still in 'uploaded' status.

    For uploaded-PDF flows. The frontend's Run-PHANTOM button hits this.
    Progress streams over WebSocket; final BATCH_COMPLETE event is emitted
    by a server-side aggregator (TODO once upload flow is in scope).
    """
    stmt = select(ApplicationORM.id).where(ApplicationORM.status == "uploaded")
    rows = (await session.execute(stmt)).all()
    application_ids = [r[0] for r in rows]

    if not application_ids:
        return BatchAnalysisLaunch(batch_id="", queued=0)

    batch_id = f"BATCH-{uuid.uuid4().hex[:12]}"
    for app_id in application_ids:
        analyze_application.delay(str(app_id))

    publish_event("ANALYSIS_STARTED", batch_id=batch_id, total=len(application_ids))
    logger.info("Queued individual analyses | batch={} | n={}", batch_id, len(application_ids))

    return BatchAnalysisLaunch(batch_id=batch_id, queued=len(application_ids))


@router.get("/status")
async def analysis_status(
    session: AsyncSession = Depends(db_session),
) -> dict:
    """Aggregate status — used by the frontend dashboard."""
    from sqlalchemy import func

    rows = (
        await session.execute(
            select(ApplicationORM.status, func.count(ApplicationORM.id))
            .group_by(ApplicationORM.status)
        )
    ).all()
    counts = {status_value: count for status_value, count in rows}

    return {
        "ws_connections": get_ws_manager().count,
        "counts_by_status": counts,
        "total": sum(counts.values()),
    }
