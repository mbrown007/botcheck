import io
import json
import logging

import structlog

from src.logging_setup import configure_logging


def _last_log_line(stream: io.StringIO) -> dict[str, object]:
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    assert lines
    return json.loads(lines[-1])


def test_configure_logging_emits_json_for_agent_structlog_events():
    stream = io.StringIO()
    configure_logging(
        service="botcheck-agent-test",
        level="INFO",
        json_logs=True,
        stream=stream,
    )
    logger = structlog.get_logger("botcheck.agent.lifecycle")
    logger.info(
        "run_started",
        run_id="run_abc",
        tenant_id="default",
        transport="sip",
    )

    payload = _last_log_line(stream)
    assert payload["event"] == "run_started"
    assert payload["run_id"] == "run_abc"
    assert payload["tenant_id"] == "default"
    assert payload["service"] == "botcheck-agent-test"


def test_configure_logging_emits_json_for_agent_stdlib_events():
    stream = io.StringIO()
    configure_logging(
        service="botcheck-agent-test",
        level="INFO",
        json_logs=True,
        stream=stream,
    )
    std_logger = logging.getLogger("botcheck.agent")
    std_logger.error("cache read failed")

    payload = _last_log_line(stream)
    assert payload["event"] == "cache read failed"
    assert payload["level"] == "error"
    assert payload["service"] == "botcheck-agent-test"
