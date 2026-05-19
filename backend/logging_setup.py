"""Centralised loguru configuration.

Called once at process start (main.py for FastAPI, celery_app.py for the
worker). Keeps formatting consistent and routes log records to:

  * stderr — pretty-coloured, level filtered by `LOG_LEVEL` env var
  * logs/phantom.log — rotating file sink, INFO+, last 5 files retained

Intercepts the stdlib `logging` module so SQLAlchemy / uvicorn / asyncio
records flow through the same sinks.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from loguru import logger

from config import PROJECT_ROOT

_LOGS_DIR = PROJECT_ROOT / "logs"
_LOGS_DIR.mkdir(parents=True, exist_ok=True)

_CONFIGURED = False


class _InterceptHandler(logging.Handler):
    """Route stdlib logging → loguru so every framework looks the same."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def configure_logging(level: str = "INFO", env: str = "development") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    logger.remove()

    fmt_console = (
        "<dim>{time:HH:mm:ss}</dim> "
        "<level>{level: <7}</level> "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
        "{message}"
    )
    fmt_file = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | "
        "{name}:{function}:{line} | {message}"
    )

    logger.add(
        sys.stderr,
        level=level.upper(),
        format=fmt_console,
        colorize=True,
        backtrace=env == "development",
        diagnose=env == "development",
    )
    logger.add(
        _LOGS_DIR / "phantom.log",
        level="INFO",
        format=fmt_file,
        rotation="5 MB",
        retention=5,
        compression="zip",
        enqueue=True,  # multiprocess-safe (Celery + uvicorn both write)
    )

    # Intercept stdlib loggers (sqlalchemy, uvicorn, neo4j…)
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for noisy in ("uvicorn.access", "uvicorn.error", "neo4j", "sqlalchemy.engine"):
        logging.getLogger(noisy).handlers = [_InterceptHandler()]
        logging.getLogger(noisy).propagate = False

    logger.info("Logging configured | level={} | env={}", level, env)
