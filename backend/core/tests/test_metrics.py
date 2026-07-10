"""Prometheus endpoint: counters, error counter, histogram buckets."""

from fastapi import Response
from fastapi.testclient import TestClient

from main import create_app
from shared.security import SecureRouter


def test_metrics_endpoint_is_public_prometheus_text() -> None:
    # context manager: one event loop for both requests (redis singleton)
    with TestClient(create_app()) as client:
        client.get("/health")
        response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    assert 'http_requests_total{method="GET",route="/health",status="200"}' in body
    assert "http_request_duration_seconds_bucket" in body


def test_5xx_increments_error_counter() -> None:
    app = create_app()
    boom = SecureRouter()

    @boom.get("/boom", public=True)
    async def boom_route() -> Response:
        raise RuntimeError("boom")

    app.include_router(boom)
    with TestClient(app, raise_server_exceptions=False) as client:
        client.get("/boom")
        body = client.get("/metrics").text
    assert 'http_request_errors_total{method="GET",route="/boom"}' in body
