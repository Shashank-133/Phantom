"""FastAPI dependency injection helpers."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from database.neo4j_client import Neo4jClient, get_neo4j
from database.postgres import get_session_factory


async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yields an async DB session per request, rolling back on errors."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def neo4j_client() -> Neo4jClient:
    return get_neo4j()
