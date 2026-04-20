from prometheus_client import Gauge, REGISTRY

from botcheck_observability import helpers


def test_counter_reuse_raises_for_wrong_collector_type(monkeypatch) -> None:
    metric_name = "test_observability_helper_counter_guard_total"
    gauge = Gauge(metric_name, "test guard collision", [])
    monkeypatch.setitem(REGISTRY._names_to_collectors, metric_name, gauge)

    try:
        helpers.counter(metric_name, "counter should not reuse gauge", [])
    except RuntimeError as exc:
        assert metric_name in str(exc)
        assert "Counter" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for wrong collector type")


def test_collector_raises_when_missing_after_duplicate_error(monkeypatch) -> None:
    metric_name = "test_observability_helper_missing_total"
    monkeypatch.delitem(REGISTRY._names_to_collectors, metric_name, raising=False)

    try:
        helpers.collector(metric_name, Gauge)
    except RuntimeError as exc:
        assert metric_name in str(exc)
        assert "not found in registry" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for missing collector")
