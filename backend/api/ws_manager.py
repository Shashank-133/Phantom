"""WebSocket connection manager.

Tracks every open browser WebSocket. The Redis bridge (api/redis_bridge.py)
hands incoming events to broadcast() which fans them out to all sockets.

Disconnections are handled gracefully — sending to a closed socket marks it
for removal but never raises out of broadcast(). This keeps the event stream
robust against flaky browsers without blocking the pipeline.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket
from loguru import logger


class WSManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        logger.info("WS connected | total={}", len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)
        logger.info("WS disconnected | total={}", len(self._connections))

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """Send a JSON payload to every connected client.

        Sockets that error during send are removed silently — we don't want
        one dead browser tab to break the broadcast loop.
        """
        if not self._connections:
            return

        # Snapshot under lock so concurrent connect/disconnect doesn't iterate-mutate.
        async with self._lock:
            sockets = list(self._connections)

        body = json.dumps(payload)
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_text(body)
            except Exception as e:
                logger.warning("WS send failed | error={}", e)
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)

    @property
    def count(self) -> int:
        return len(self._connections)


_manager: WSManager | None = None


def get_ws_manager() -> WSManager:
    global _manager
    if _manager is None:
        _manager = WSManager()
    return _manager
