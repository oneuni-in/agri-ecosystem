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
    "/ads/serve",
    "/ads/impressions",
    "/ads/clicks",
    # A-U4 W1: one boolean — is the assistant switched on. The web app needs
    # it before login to choose between the chat and the honest not-yet
    # state, and /ai/ask cannot answer (auth runs before the flag check).
    "/ai/status",
    "/billing/webhook/razorpay",
    "/catalog/verticals/{vertical}/schema",
    "/catalog/verticals",
    "/catalog/products/{slug}",
    "/catalog/businesses/{slug}/products",
    "/catalog/verticals/{vertical}/products",
    "/catalog/milk/coverage/pincodes",
    "/catalog/milk/home/{pincode}",
    # A-U4 W2: the active earn rules (code, amount, caps). Public because
    # the home's "Earn AgriCoins" cards render for logged-out visitors and
    # must show the real configured amount, not the mockup's placeholder.
    "/coins/rules",
    # A-U3 W1/W2 — the content engine's reader surface. Approved items
    # only; the gate is structural in service._published().
    "/content/feed",
    "/content/items/{slug}",
    "/content/advisories",
    "/directory/categories/active",
    "/directory/businesses/{slug}",
    "/directory/covers/{pincode}",
    "/directory/businesses/{slug}/nearby-branches",
    "/directory/businesses/{slug}/view",
    # A-U4b O11 (AG-A69): the "Live on agri.in" feed read. agri_live_feed-
    # gated (404 while off — its D57 state); every field it serves is
    # already public elsewhere or coarse, per
    # docs/security/agri-live-feed-privacy.md.
    "/directory/feed/live",
    # Phase 2: the agri-colleges vertical. Read-only reference data about
    # public institutions -- the same class as /catalog/verticals and
    # /market/schemes. app_rt holds SELECT only on education.*, so there is
    # no write route to declare and none to forget.
    "/education/institutions",
    "/education/institutions/{slug}",
    "/education/states",
    "/education/programmes",
    "/education/student-resources",
    "/education/student-resources/{slug}",
    "/education/guides",
    "/education/guides/{slug}",
    "/authorize",
    "/token",
    "/oauth/revoke",
    "/.well-known/jwks.json",
    "/auth/otp/request",
    "/auth/otp/verify",
    "/auth/login",
    "/leads/inquiries",
    "/leads/pincode-interest",
    "/market/today/{pincode}",  # agri_today-gated home Today payload
    # A-U2 W3 commodity pages. Ungated on purpose: agri_today is the
    # HOME strip's kill switch, and these are indexed SEO pages.
    "/market/commodities",
    "/market/commodities/{slug}",
    # A-U3 W2 — published government helpline numbers and scheme cards.
    "/market/helplines",
    "/market/schemes",
    "/reviews",
    "/reviews/summary",
    # A-U4 W3 (D64): cross-vertical search for the hub. Same public read
    # class as /search, queried across every site index. Listed before
    # "/search" because that is the order the router registers them.
    "/search/federated",
    "/search",
    "/identity/location",
]


def test_public_routes_are_exactly_the_declared_endpoints() -> None:
    app = create_app()
    assert app.state.public_routes == EXPECTED_PUBLIC_ROUTES


def test_boot_log_lists_public_routes(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO), TestClient(create_app()):
        pass
    assert f"public routes: {EXPECTED_PUBLIC_ROUTES}" in caplog.text
