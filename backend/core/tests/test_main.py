"""App factory wiring: health endpoints public, everything else absent/private,
public-route registry logged on boot."""

import logging

import pytest
from fastapi.testclient import TestClient

from main import create_app


def test_health_is_public() -> None:
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_deep_reports_per_service_status() -> None:
    # no backing services running in unit tests -> degraded 503 with all-False map
    response = TestClient(create_app()).get("/health/deep")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert set(body["services"]) == {"postgres", "redis", "meilisearch", "minio"}
    assert all(up is False for up in body["services"].values())


def test_public_routes_are_exactly_the_health_endpoints() -> None:
    app = create_app()
    assert app.state.public_routes == ["/health", "/health/deep"]


def test_boot_log_lists_public_routes(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO), TestClient(create_app()):
        pass
    assert "public routes: ['/health', '/health/deep']" in caplog.text
