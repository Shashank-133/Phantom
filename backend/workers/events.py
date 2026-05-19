"""Event publishing — Celery → Redis pubsub → FastAPI WebSocket clients.

Celery workers and the FastAPI process are isolated. To deliver real-time
updates to the browser, workers publish JSON events to a Redis pubsub channel
and FastAPI subscribes to that channel (api/redis_bridge.py) and broadcasts
each event to all connected WebSocket clients.

Event schema (always a dict with a "type" key):

    {"type": "ANALYSIS_STARTED",    "batch_id": "...", "total": 40}
    {"type": "DOCUMENT_ANALYZED",   "application_id": "...", "progress": "1/40",
                                     "cbs_match_score": 0.43, "origin_tool": "Canva 2.0",
                                     "tool_category": "consumer_design_tool"}
    {"type": "GRAPH_BUILT",         "nodes": 40, "edges_by_type": {...}}
    {"type": "RING_DETECTED",       "ring_id": "RING-...", "ring_size": 11,
                                     "phantom_score": 0.97, "recommended_action": "FREEZE_AND_ESCALATE",
                                     "report": {...}}
    {"type": "BATCH_COMPLETE",      "batch_id": "...", "rings": [...], "graph_data": {...}}
    {"type": "ERROR",               "message": "..."}

All events are timestamped at publish time.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import redis
from loguru import logger

from config import get_settings

PHANTOM_EVENTS_CHANNEL = "phantom:events"

_publisher: redis.Redis | None = None


def _get_publisher() -> redis.Redis:
    """Synchronous Redis client used by Celery workers to publish events."""
    global _publisher
    if _publisher is None:
        settings = get_settings()
        _publisher = redis.from_url(settings.redis_url, decode_responses=True)
    return _publisher


def publish_event(event_type: str, **payload: Any) -> None:
    """Publish a structured event to the WS broadcast channel.

    Never raises — Redis being unavailable should not crash an analysis job.
    """
    event = {
        "type": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        **payload,
    }
    try:
        body = json.dumps(event, default=_json_default)
        _get_publisher().publish(PHANTOM_EVENTS_CHANNEL, body)
    except Exception as e:
        logger.error("publish_event failed | type={} | error={}", event_type, e)


def _json_default(value: Any) -> Any:
    from uuid import UUID

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "value"):  # Enums
        return value.value
    if hasattr(value, "model_dump"):  # pydantic models
        return value.model_dump(mode="json")
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
