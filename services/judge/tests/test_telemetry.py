import os

from botcheck_judge import telemetry


def test_instrument_httpx_missing_module_fails_open(monkeypatch, caplog):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://alloy:4318")
    monkeypatch.setattr(telemetry, "_import_optional_module", lambda _name: None)

    telemetry.instrument_httpx()

    assert "package missing" in caplog.text.lower()


def test_init_llm_instrumentation_missing_module_fails_open(monkeypatch, caplog):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://alloy:4318")
    monkeypatch.setattr(telemetry, "_import_optional_module", lambda _name: None)

    telemetry.init_llm_instrumentation()

    assert "package missing" in caplog.text.lower()


def test_instrumentation_noop_when_otel_disabled(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.setattr(telemetry, "_import_optional_module", lambda _name: (_ for _ in ()).throw(AssertionError("should not import")))

    telemetry.instrument_httpx()
    telemetry.init_llm_instrumentation()

    assert os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") in (None, "")
