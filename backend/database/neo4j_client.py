"""Async Neo4j client wrapper.

Used by services/graph_builder.py (Day 4) to upsert Application nodes and
their relationship edges, and by services/community_detection.py to read
the graph back into NetworkX for Louvain.

Constraints created at startup: every Application node has a unique id.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from loguru import logger
from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession

from config import get_settings


class Neo4jClient:
    """Thin async wrapper around the official neo4j driver."""

    def __init__(self) -> None:
        settings = get_settings()
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_pool_size=20,
        )
        self._uri = settings.neo4j_uri

    async def close(self) -> None:
        await self._driver.close()

    def session(self) -> AsyncSession:
        """Open an async session. Caller is responsible for closing it."""
        return self._driver.session()

    async def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        """Run a single Cypher query and return all records as dicts."""
        async with self._driver.session() as session:
            result = await session.run(query, **params)
            return [dict(record) async for record in result]

    async def run_write_tx(self, query: str, **params: Any) -> list[dict[str, Any]]:
        """Run a Cypher query inside a managed write transaction."""
        async with self._driver.session() as session:
            return await session.execute_write(_run_query, query, params)

    async def batch_write(self, query: str, batch: list[dict[str, Any]]) -> None:
        """Run a parameterized Cypher query once per item in `batch`.

        Wrapped in a single transaction so 40 application upserts feel like one.
        Used by graph_builder for bulk node/edge creation.
        """
        async with self._driver.session() as session:
            async with await session.begin_transaction() as tx:
                for params in batch:
                    await tx.run(query, **params)

    async def ensure_constraints(self) -> None:
        """Create constraints + indexes. Idempotent — uses IF NOT EXISTS."""
        statements = [
            "CREATE CONSTRAINT app_id_unique IF NOT EXISTS "
            "FOR (a:Application) REQUIRE a.id IS UNIQUE",
            "CREATE INDEX app_font_hash IF NOT EXISTS "
            "FOR (a:Application) ON (a.font_subset_hash)",
            "CREATE INDEX app_origin_tool IF NOT EXISTS "
            "FOR (a:Application) ON (a.origin_tool)",
            "CREATE INDEX app_submission_time IF NOT EXISTS "
            "FOR (a:Application) ON (a.submission_time)",
        ]
        async with self._driver.session() as session:
            for stmt in statements:
                await session.run(stmt)
        logger.info("Neo4j constraints + indexes ensured")

    async def ping(self) -> bool:
        try:
            async with self._driver.session() as session:
                result = await session.run("RETURN 1 AS ok")
                rec = await result.single()
                return rec is not None and rec["ok"] == 1
        except Exception as e:
            logger.error("Neo4j ping failed: {}", e)
            return False

    async def clear_graph(self) -> None:
        """Wipe all nodes and relationships. Used by seed script / tests."""
        await self.run("MATCH (n) DETACH DELETE n")
        logger.warning("Neo4j graph cleared")


async def _run_query(tx: Any, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    result = await tx.run(query, **params)
    return [dict(record) async for record in result]


_client: Neo4jClient | None = None


@lru_cache
def get_neo4j() -> Neo4jClient:
    """Singleton accessor. The driver itself maintains the connection pool."""
    global _client
    if _client is None:
        _client = Neo4jClient()
        logger.info("Neo4j client initialized")
    return _client
