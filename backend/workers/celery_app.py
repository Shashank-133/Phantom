"""Celery application configuration.

The Celery worker runs in a separate process from FastAPI. It picks tasks off
the Redis broker, runs the analysis pipeline, and publishes progress events to
a Redis pubsub channel that FastAPI subscribes to (see api/redis_bridge.py).

To run a worker (host-side dev, Windows):
    .venv/Scripts/python.exe -m celery -A workers.celery_app worker --loglevel=info --pool=solo

The `--pool=solo` flag is required on Windows because Celery's default
prefork pool does not work well there. In Docker (Linux), the default
prefork pool works fine and we get real parallelism.
"""
from __future__ import annotations

from celery import Celery
from loguru import logger

from config import get_settings
from logging_setup import configure_logging

settings = get_settings()
configure_logging(settings.log_level, settings.env)

celery_app = Celery(
    "phantom",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["workers.tasks"],
)

celery_app.conf.update(
    # Task routing / serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Don't lose progress on a worker crash
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Stop runaway tasks — analyzing 40 docs should take well under 5 min total
    task_soft_time_limit=600,
    task_time_limit=900,
    # Limit prefetch so progress updates appear in real time as tasks complete
    worker_prefetch_multiplier=1,
    # Result backend retention — only keep results for 1 hour (we use Postgres for durability)
    result_expires=3600,
)

logger.info("Celery configured | broker={} | backend={}", settings.celery_broker_url, settings.celery_result_backend)
