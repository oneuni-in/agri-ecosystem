"""Prometheus-format process metrics (D05).

Right-sized per ADR-0011: no Prometheus server ships. Netdata on the VPS (or
any scraper) reads GET /metrics. The route label is always the matched route
template, never the raw path, to bound label cardinality.
"""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

registry = CollectorRegistry()

REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests processed",
    ["method", "route", "status"],
    registry=registry,
)
ERRORS = Counter(
    "http_request_errors_total",
    "HTTP requests that returned a 5xx",
    ["method", "route"],
    registry=registry,
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "Request wall time; p95 is derived from these buckets",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 6.4),
    registry=registry,
)


def observe_request(method: str, route: str, status: int, seconds: float) -> None:
    REQUESTS.labels(method, route, str(status)).inc()
    LATENCY.labels(method, route).observe(seconds)
    if status >= 500:
        ERRORS.labels(method, route).inc()


def render() -> tuple[bytes, str]:
    return generate_latest(registry), CONTENT_TYPE_LATEST


def reset_metrics() -> None:
    """Test hook (tests/conftest.py): drop label children between tests."""
    for metric in (REQUESTS, ERRORS, LATENCY):
        metric.clear()
