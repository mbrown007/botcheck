from __future__ import annotations

from botcheck_api import metrics


def test_shared_provider_metric_labels_match_contract() -> None:
    assert tuple(metrics.PROVIDER_API_CALLS_TOTAL._labelnames) == (
        "provider",
        "service",
        "model",
        "outcome",
    )
    assert tuple(metrics.TTS_CHARACTERS_TOTAL._labelnames) == (
        "provider",
        "model",
        "scenario_kind",
    )
    assert tuple(metrics.STT_SECONDS_TOTAL._labelnames) == (
        "provider",
        "model",
        "scenario_kind",
    )
    assert tuple(metrics.PROVIDER_CIRCUIT_TRANSITIONS_TOTAL._labelnames) == (
        "provider",
        "service",
        "component",
        "from_state",
        "to_state",
    )
    assert tuple(metrics.PROVIDER_CIRCUIT_REJECTIONS_TOTAL._labelnames) == (
        "provider",
        "service",
        "component",
    )
    assert tuple(metrics.PROVIDER_CIRCUIT_STATE._labelnames) == (
        "source",
        "provider",
        "service",
        "component",
        "state",
    )
