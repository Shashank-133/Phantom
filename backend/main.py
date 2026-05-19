"""PHANTOM backend — FastAPI entrypoint.

Lifespan responsibilities (run once at startup, before any request lands):
  1. Create Postgres tables (database.postgres.create_tables)
  2. Ensure Neo4j constraints + indexes (database.neo4j_client.ensure_constraints)
  3. Preload the CBS reference corpus and ViT model (best-effort, non-fatal)
  4. Seed the demo data if the applications table is empty
  5. Start the Redis pubsub bridge → fans Celery events to WebSocket clients

The startup is best-effort: any individual step that fails is logged but does
NOT prevent the API from coming online. /health surfaces the real readiness
status so the frontend can show degraded-mode warnings if needed.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.redis_bridge import get_redis_bridge
from api.routes import analyze as analyze_routes
from api.routes import evidence as evidence_routes
from api.routes import results as results_routes
from api.routes import ws as ws_routes
from config import get_settings
from database.neo4j_client import get_neo4j
from database.postgres import create_tables, get_session_factory, ping as pg_ping
from logging_setup import configure_logging

settings = get_settings()
configure_logging(settings.log_level, settings.env)


async def _startup() -> dict:
    """Run all startup steps, collect status, return a summary for /health."""
    status = {
        "postgres_tables": False,
        "neo4j_constraints": False,
        "cbs_reference_loaded": False,
        "vit_preloaded": False,
        "embedding_preloaded": False,
        "demo_seeded": False,
        "demo_count": 0,
        "redis_bridge": False,
    }

    # 1. Postgres schema
    try:
        await create_tables()
        status["postgres_tables"] = True
    except Exception as e:
        logger.error("Postgres table creation failed: {}", e)

    # 2. Neo4j constraints
    neo4j = get_neo4j()
    try:
        await neo4j.ensure_constraints()
        status["neo4j_constraints"] = True
    except Exception as e:
        logger.error("Neo4j constraint creation failed: {}", e)

    # 3. CBS reference + ML model preload (lazy; best-effort, non-fatal)
    try:
        from services.origin_engine import _get_cbs_reference

        cbs = _get_cbs_reference()
        status["cbs_reference_loaded"] = cbs is not None
    except Exception as e:
        logger.warning("CBS reference preload skipped: {}", e)

    try:
        from ml.vit_inference import preload as preload_vit

        status["vit_preloaded"] = preload_vit()
    except Exception as e:
        logger.warning("ViT preload skipped: {}", e)

    try:
        from ml.embedding_model import preload as preload_embed

        status["embedding_preloaded"] = preload_embed()
    except Exception as e:
        logger.warning("Embedding model preload skipped: {}", e)

    # 4. Demo data seeding
    try:
        from seed.init_demo_data import seed_if_empty
        from sqlalchemy import func, select

        from database.models import ApplicationORM

        session_factory = get_session_factory()
        async with session_factory() as session:
            seeded = await seed_if_empty(session, neo4j)
            status["demo_seeded"] = seeded
            count_result = await session.execute(select(func.count()).select_from(ApplicationORM))
            status["demo_count"] = count_result.scalar_one()
    except Exception as e:
        logger.warning("Demo seed skipped: {}", e)

    # 5. Redis bridge — start AFTER ML preload so the bridge is the last thing
    #    we leave running in the event loop.
    try:
        get_redis_bridge().start()
        status["redis_bridge"] = True
    except Exception as e:
        logger.error("Redis bridge failed to start: {}", e)

    return status


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("PHANTOM backend starting | env={} | log_level={}", settings.env, settings.log_level)
    app.state.startup_status = await _startup()
    logger.info("Startup status: {}", app.state.startup_status)
    yield
    logger.info("PHANTOM backend shutting down")
    try:
        await get_redis_bridge().stop()
    except Exception:
        pass
    try:
        await get_neo4j().close()
    except Exception:
        pass


app = FastAPI(
    title="PHANTOM",
    description="Fraud Ring & Document Origin Intelligence Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(analyze_routes.router)
app.include_router(results_routes.router)
app.include_router(evidence_routes.router)
app.include_router(ws_routes.router)


@app.get("/health")
async def health():
    """Liveness + readiness.

    Pings Postgres + Neo4j live, then layers on the startup snapshot plus
    current ML model + narrative-backend availability. The frontend uses
    `status` ("ok" / "degraded") to colour the status dot; the detailed
    breakdown is exposed so judges can satisfy themselves that nothing is
    being faked at runtime.
    """
    from services.narrative_writer import narrative_source_info
    from services.origin_engine import diagnostics as origin_diagnostics

    neo4j = get_neo4j()
    pg_ok = await pg_ping()
    neo_ok = await neo4j.ping()
    status_dict = getattr(app.state, "startup_status", {})

    overall = "ok" if (pg_ok and neo_ok) else "degraded"

    return {
        "status": overall,
        "service": "phantom-backend",
        "version": app.version,
        "env": settings.env,
        "checks": {
            "postgres": pg_ok,
            "neo4j": neo_ok,
        },
        "startup": status_dict,
        "ml": origin_diagnostics(),
        "narrative": narrative_source_info(),
    }


@app.get("/")
async def root():
    return {
        "service": "PHANTOM",
        "tagline": "Where was this document born?",
        "docs": "/docs",
        "websocket": "/ws",
        "demo_endpoint": "POST /analyze/demo",
    }
