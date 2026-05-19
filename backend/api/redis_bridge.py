"""Redis pub/sub bridge — Celery → FastAPI WebSocket.

Celery workers publish JSON events to the `phantom:events` channel
(workers/events.py). This module runs an asyncio task that subscribes to that
channel and broadcasts every received message to all connected WS clients
(api/ws_manager.py).

The subscriber is started from main.py's lifespan and cancelled on shutdown.
If Redis is unavailable, the task logs warnings and retries with backoff —
it never crashes the API.
"""
from __future__ import annotations

import asyncio
import json

import redis.asyncio as aioredis
from loguru import logger

from api.ws_manager import get_ws_manager
from config import get_settings
from workers.events import PHANTOM_EVENTS_CHANNEL


_RECONNECT_BACKOFF_SECONDS = (1, 2, 5, 10, 30)


class RedisBridge:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run(), name="phantom-redis-bridge")
            logger.info("Redis bridge started")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("Redis bridge stopped")

    async def _run(self) -> None:
        settings = get_settings()
        ws_manager = get_ws_manager()
        attempt = 0

        while not self._stop_event.is_set():
            try:
                client = aioredis.from_url(settings.redis_url, decode_responses=True)
                pubsub = client.pubsub()
                await pubsub.subscribe(PHANTOM_EVENTS_CHANNEL)
                logger.info("Subscribed to Redis channel '{}'", PHANTOM_EVENTS_CHANNEL)
                attempt = 0

                async for message in pubsub.listen():
                    if self._stop_event.is_set():
                        break
                    if message is None or message.get("type") != "message":
                        continue

                    raw = message.get("data")
                    try:
                        payload = json.loads(raw)
                    except (TypeError, ValueError) as e:
                        logger.warning("Discarding malformed pubsub message: {}", e)
                        continue

                    await ws_manager.broadcast(payload)

                await pubsub.unsubscribe(PHANTOM_EVENTS_CHANNEL)
                await client.close()

            except asyncio.CancelledError:
                raise
            except Exception as e:
                wait = _RECONNECT_BACKOFF_SECONDS[min(attempt, len(_RECONNECT_BACKOFF_SECONDS) - 1)]
                logger.error("Redis bridge error: {} — retrying in {}s", e, wait)
                attempt += 1
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=wait)
                except asyncio.TimeoutError:
                    pass


_bridge: RedisBridge | None = None


def get_redis_bridge() -> RedisBridge:
    global _bridge
    if _bridge is None:
        _bridge = RedisBridge()
    return _bridge
