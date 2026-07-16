"""App factory wiring: health endpoints public, everything else absent/private,
public-route registry logged on boot."""

import logging

import pytest
from fastapi.testclient import TestClient

from main import create_app
from settings import get_settings
from shared.cache import reset_redis
from shared.db import reset_engine


def test_health_is_public() -> None:
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_deep_reports_per_service_status(monkeypatch: pytest.MonkeyPatch) -> None:
    # point every service at a closed port -> degraded 503 with all-False map,
    # regardless of whether the dev compose stack happens to be running
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@127.0.0.1:1/agri")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("MEILISEARCH_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://127.0.0.1:1")
    get_settings.cache_clear()
    reset_engine()
    reset_redis()
    response = TestClient(create_app()).get("/health/deep")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert set(body["services"]) == {"postgres", "redis", "meilisearch", "minio"}
    assert all(up is False for up in body["services"].values())


EXPECTED_PUBLIC_ROUTES = [
    "/health",
    "/health/deep",
    "/metrics",
    "/directory/businesses/{slug}",
    "/directory/covers/{pincode}",
    "/authorize",
    "/token",
    "/oauth/revoke",
    "/.well-known/jwks.json",
    "/auth/otp/request",
    "/auth/otp/verify",
    "/auth/login",
]


def test_public_routes_are_exactly_the_declared_endpoints() -> None:
    app = create_app()
    assert app.state.public_routes == EXPECTED_PUBLIC_ROUTES


def test_boot_log_lists_public_routes(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO), TestClient(create_app()):
        pass
    assert f"public routes: {EXPECTED_PUBLIC_ROUTES}" in caplog.text
