"""
OpenTelemetry tracing setup for the BotCheck Harness Agent.

No-op when OTEL_EXPORTER_OTLP_ENDPOINT is not set.
"""
from __future__ import annotations

import logging
import os

from botcheck_observability.trace_contract import (
    attach_trace_context_from_carrier,
    detach_trace_context,
    inject_trace_context_into_headers,
)

logger = logging.getLogger(__name__)


def setup_tracing(service_name: str) -> None:
    """Configure OTLP trace export.

    Reads standard OTEL environment variables:
      OTEL_EXPORTER_OTLP_ENDPOINT  e.g. http://alloy:4318
      OTEL_SERVICE_NAME            overrides the service_name argument
    """
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return

    from opentelemetry import trace  # noqa: PLC0415
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # noqa: PLC0415
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource  # noqa: PLC0415
    from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
    from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415

    name = os.getenv("OTEL_SERVICE_NAME", service_name)
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    logger.info("Tracing enabled — service=%s endpoint=%s", name, endpoint)


def instrument_httpx() -> None:
    """Instrument all httpx clients — traces BotCheck API callbacks."""
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip():
        return

    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # noqa: PLC0415

    HTTPXClientInstrumentor().instrument()
    logger.info("httpx auto-instrumentation active")
