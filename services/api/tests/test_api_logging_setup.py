import io
import json
import logging

import structlog

from botcheck_api.logging_setup import configure_logging


def _last_log_line(stream: io.StringIO) -> dict[str, object]:
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    assert lines
    return json.loads(lines[-1])


def test_configure_logging_emits_json_for_structlog_events():
    stream = io.StringIO()
    configure_logging(
        service="botcheck-api-test",
        level="INFO",
        json_logs=True,
        stream=stream,
    )
    logger = structlog.get_logger("botcheck.api.test")
    logger.info(
        "run_started",
        run_id="run_123",
        tenant_id="default",
        transport="sip",
    )

    payload = _last_log_line(stream)
    assert payload["event"] == "run_started"
    assert payload["run_id"] == "run_123"
    assert payload["tenant_id"] == "default"
    assert payload["transport"] == "sip"
    assert payload["service"] == "botcheck-api-test"


def test_configure_logging_emits_json_for_stdlib_events():
    stream = io.StringIO()
    configure_logging(
        service="botcheck-api-test",
        level="INFO",
        json_logs=True,
        stream=stream,
    )
    std_logger = logging.getLogger("botcheck.api.test")
    std_logger.warning("arq queue unavailable")

    payload = _last_log_line(stream)
    assert payload["event"] == "arq queue unavailable"
    assert payload["level"] == "warning"
    assert payload["service"] == "botcheck-api-test"
