"""WebSocket route — frontend connects here for real-time events."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from api.ws_manager import get_ws_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    manager = get_ws_manager()
    await manager.connect(ws)

    # Send a hello so the frontend knows the connection is alive.
    try:
        await ws.send_json({"type": "WS_CONNECTED", "active_connections": manager.count})
    except Exception:
        pass

    try:
        while True:
            # We don't expect inbound messages, but read to detect disconnects.
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WS unexpected error: {}", e)
    finally:
        await manager.disconnect(ws)
