"""
OpenTelemetry tracing setup for the BotCheck Judge worker.

No-op when OTEL_EXPORTER_OTLP_ENDPOINT is not set.
"""
from __future__ import annotations

import importlib
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


def _import_optional_module(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        return None


def instrument_httpx() -> None:
    """Instrument all httpx clients — traces Anthropic + BotCheck API calls."""
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip():
        return

    module = _import_optional_module("opentelemetry.instrumentation.httpx")
    if module is None:
        logger.warning("httpx OpenTelemetry instrumentation package missing; continuing")
        return

    instrumentor_cls = getattr(module, "HTTPXClientInstrumentor", None)
    if instrumentor_cls is None:
        logger.warning("HTTPXClientInstrumentor not found in httpx instrumentation module")
        return

    try:
        instrumentor_cls().instrument()
    except Exception:
        logger.warning("Failed to enable httpx OpenTelemetry instrumentation", exc_info=True)
        return
    logger.info("httpx auto-instrumentation active")


def init_llm_instrumentation() -> None:
    """Instrument Anthropic client for LLM token/cost/latency traces.

    Uses opentelemetry-instrumentation-anthropic (OTel GenAI semantic conventions).
    No-op when OTEL_EXPORTER_OTLP_ENDPOINT is not set.
    Must be called before any anthropic.AsyncAnthropic client is created.
    """
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip():
        return

    module = _import_optional_module("opentelemetry.instrumentation.anthropic")
    if module is None:
        logger.warning("Anthropic OpenTelemetry instrumentation package missing; continuing")
        return

    instrumentor_cls = getattr(module, "AnthropicInstrumentor", None)
    if instrumentor_cls is None:
        logger.warning("AnthropicInstrumentor not found in anthropic instrumentation module")
        return

    try:
        instrumentor_cls().instrument()
    except Exception:
        logger.warning("Failed to enable Anthropic OpenTelemetry instrumentation", exc_info=True)
        return
    logger.info("Anthropic LLM instrumentation active")
