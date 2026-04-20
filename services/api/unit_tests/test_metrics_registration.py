from prometheus_client import Gauge, REGISTRY

from botcheck_api import metrics


def test_counter_reuse_raises_for_wrong_collector_type(monkeypatch) -> None:
    metric_name = "test_api_counter_registration_guard_total"
    gauge = Gauge(metric_name, "test guard collision", [])
    monkeypatch.setitem(REGISTRY._names_to_collectors, metric_name, gauge)

    try:
        metrics._counter(metric_name, "counter should not reuse gauge", [])
    except RuntimeError as exc:
        assert metric_name in str(exc)
        assert "Counter" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for wrong collector type")
