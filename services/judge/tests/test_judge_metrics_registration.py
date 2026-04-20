import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")

from prometheus_client import Gauge, Histogram, REGISTRY

from botcheck_judge import metrics


def test_gauge_reuse_raises_for_wrong_collector_type(monkeypatch) -> None:
    metric_name = "test_judge_gauge_registration_guard"
    histogram = Histogram(metric_name, "test guard collision", [])
    monkeypatch.setitem(REGISTRY._names_to_collectors, metric_name, histogram)

    try:
        metrics._gauge(metric_name, "gauge should not reuse histogram", [])
    except RuntimeError as exc:
        assert metric_name in str(exc)
        assert "Gauge" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for wrong collector type")


def test_voice_quality_percentage_histograms_use_strictly_positive_buckets() -> None:
    for histogram in (
        metrics.VOICE_QUALITY_INTERRUPTION_RECOVERY_PCT,
        metrics.VOICE_QUALITY_TURN_TAKING_EFFICIENCY_PCT,
    ):
        assert histogram._upper_bounds[0] == 0.001


def test_voice_quality_response_gap_metric_is_gauge() -> None:
    assert isinstance(metrics.VOICE_QUALITY_P95_RESPONSE_GAP_MILLISECONDS, Gauge)
