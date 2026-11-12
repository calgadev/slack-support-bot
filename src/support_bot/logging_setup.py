"""structlog configuration: one JSON object per line on stdout.

Logs from the standard library (slack_bolt, httpx, chromadb...) go through the same
JSON renderer, so the whole process emits a single machine-readable format.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_SHARED_PROCESSORS: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
]

_NOISY_LOGGERS = ("httpx", "httpx2", "httpcore", "chromadb", "slack_sdk.socket_mode", "urllib3")


def configure_logging(level: str = "INFO") -> None:
    log_level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(log_level)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(max(log_level, logging.WARNING))


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
