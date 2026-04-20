"""
OpenTelemetry tracing setup for the BotCheck API.

No-op when OTEL_EXPORTER_OTLP_ENDPOINT is not set, so local dev
requires no configuration changes.
"""
from __future__ import annotations

import logging
import os

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


def instrument_app(app: object) -> None:
    """Attach FastAPI + httpx auto-instrumentation after the app is created."""
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip():
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # noqa: PLC0415
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # noqa: PLC0415

    FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]
    HTTPXClientInstrumentor().instrument()
    logger.info("FastAPI + httpx auto-instrumentation active")


def init_llm_instrumentation() -> None:
    """Instrument OpenAI client for LLM token/cost/latency traces.

    Uses opentelemetry-instrumentation-openai-v2 (OTel GenAI semantic conventions).
    No-op when OTEL_EXPORTER_OTLP_ENDPOINT is not set.
    Must be called before any openai.AsyncOpenAI client is created.
    """
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip():
        return

    from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor  # noqa: PLC0415

    OpenAIInstrumentor().instrument()
    logger.info("OpenAI LLM instrumentation active")
