from prometheus_client import Counter, REGISTRY

from src import metrics


def test_histogram_reuse_raises_for_wrong_collector_type(monkeypatch) -> None:
    metric_name = "test_agent_histogram_registration_guard_seconds"
    counter = Counter(metric_name, "test guard collision", [])
    monkeypatch.setitem(REGISTRY._names_to_collectors, metric_name, counter)

    try:
        metrics._histogram(metric_name, "histogram should not reuse counter", [], (0.1, 1.0))
    except RuntimeError as exc:
        assert metric_name in str(exc)
        assert "Histogram" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for wrong collector type")
