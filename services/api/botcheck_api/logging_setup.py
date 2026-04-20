from __future__ import annotations

import logging
import sys
from typing import TextIO

import structlog


def _parse_level(level: str) -> int:
    candidate = (level or "INFO").strip().upper()
    parsed = logging.getLevelName(candidate)
    return parsed if isinstance(parsed, int) else logging.INFO


def _add_service_processor(service: str):
    def _processor(_, __, event_dict: dict):
        event_dict["service"] = service
        return event_dict

    return _processor


def configure_logging(
    *,
    service: str,
    level: str = "INFO",
    json_logs: bool = True,
    stream: TextIO | None = None,
) -> None:
    """
    Configure structured logging for botcheck.* loggers.

    `botcheck` logger is configured as a boundary so service logs are structured
    while third-party loggers keep their own formatting.
    """
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    add_service = _add_service_processor(service)
    pre_chain = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        add_service,
    ]
    renderer = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer()
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=pre_chain,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(formatter)

    botcheck_logger = logging.getLogger("botcheck")
    botcheck_logger.handlers.clear()
    botcheck_logger.setLevel(_parse_level(level))
    botcheck_logger.propagate = False
    botcheck_logger.addHandler(handler)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            timestamper,
            add_service,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
