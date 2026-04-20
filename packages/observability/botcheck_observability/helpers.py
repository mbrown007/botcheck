from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, REGISTRY


def collector(
    name: str,
    expected_type: type[Counter] | type[Gauge] | type[Histogram],
) -> Counter | Gauge | Histogram:
    existing = REGISTRY._names_to_collectors.get(name)
    if existing is None:
        raise RuntimeError(
            f"Collector '{name}' not found in registry after duplicate registration error"
        )
    if isinstance(existing, expected_type):
        return existing
    raise RuntimeError(
        f"Collector '{name}' already exists but is not a {expected_type.__name__}"
    )


def counter(name: str, doc: str, labels: list[str]) -> Counter:
    try:
        return Counter(name, doc, labels)
    except ValueError:
        return collector(name, Counter)  # type: ignore[return-value]  # narrowed by collector


def histogram(name: str, doc: str, labels: list[str], buckets: tuple[float, ...]) -> Histogram:
    try:
        return Histogram(name, doc, labels, buckets=buckets)
    except ValueError:
        return collector(name, Histogram)  # type: ignore[return-value]  # narrowed by collector


def gauge(name: str, doc: str, labels: list[str] | None = None) -> Gauge:
    label_names = labels or []
    try:
        return Gauge(name, doc, label_names)
    except ValueError:
        return collector(name, Gauge)  # type: ignore[return-value]  # narrowed by collector
