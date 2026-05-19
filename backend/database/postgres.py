"""Async Postgres client — SQLAlchemy 2.0 + asyncpg.

Wires the connection pool, session factory, and declarative Base. Tables
themselves are defined in backend/database/models.py (Day 3) and created at
FastAPI startup by main.py's lifespan via create_tables().
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM models."""

    pass


@lru_cache
def get_engine() -> AsyncEngine:
    """Single global engine. Pooled, async."""
    settings = get_settings()
    engine = create_async_engine(
        settings.postgres_dsn,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    logger.info(
        "Postgres engine created | host={}:{} | db={}",
        settings.postgres_host,
        settings.postgres_port,
        settings.postgres_db,
    )
    return engine


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session per request, closes on exit."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables() -> None:
    """Create all tables declared on Base.metadata.

    Idempotent — safe to call on every startup. Called by main.py lifespan.
    """
    engine = get_engine()
    # Import models so they're registered with Base.metadata.
    # Done lazily here to avoid circular imports at module load.
    try:
        from database import models as _  # noqa: F401
    except ImportError:
        logger.debug("database.models not present yet — skipping table create")
        return

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Postgres tables ensured")


async def ping() -> bool:
    """Connectivity check for /health endpoint."""
    from sqlalchemy import text

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("Postgres ping failed: {}", e)
        return False
