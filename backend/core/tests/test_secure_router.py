"""The Constitution's core guarantee: a thoughtlessly-added route is private
and rate-limited. THE test: no public=True -> 401."""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel

from settings import get_settings
from shared.security import SecureRouter, client_ip


class Message(BaseModel):
    detail: str


def make_client(router: SecureRouter) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_route_without_public_returns_401() -> None:
    router = SecureRouter()

    @router.get("/private")
    async def private_route() -> Message:  # pragma: no cover - never reached
        return Message(detail="secret")

    assert make_client(router).get("/private").status_code == 401


def test_all_verbs_are_private_by_default() -> None:
    router = SecureRouter()

    @router.post("/w")
    async def w() -> Message:  # pragma: no cover
        return Message(detail="w")

    @router.put("/x")
    async def x() -> Message:  # pragma: no cover
        return Message(detail="x")

    @router.patch("/y")
    async def y() -> Message:  # pragma: no cover
        return Message(detail="y")

    @router.delete("/z")
    async def z() -> Message:  # pragma: no cover
        return Message(detail="z")

    client = make_client(router)
    assert client.post("/w").status_code == 401
    assert client.put("/x").status_code == 401
    assert client.patch("/y").status_code == 401
    assert client.delete("/z").status_code == 401


def test_public_route_bypasses_auth() -> None:
    router = SecureRouter()

    @router.get("/open", public=True)
    async def open_route() -> Message:
        return Message(detail="hello")

    response = make_client(router).get("/open")
    assert response.status_code == 200
    assert response.json() == {"detail": "hello"}


def test_public_route_recorded_with_router_prefix() -> None:
    router = SecureRouter(prefix="/demo")

    @router.get("/open", public=True)
    async def open_route() -> Message:  # pragma: no cover
        return Message(detail="hello")

    assert router.public_paths == ["/demo/open"]


def test_private_route_not_in_public_paths() -> None:
    router = SecureRouter()

    @router.get("/private")
    async def private_route() -> Message:  # pragma: no cover
        return Message(detail="secret")

    assert router.public_paths == []


def test_route_without_response_model_is_rejected() -> None:
    router = SecureRouter()
    with pytest.raises(RuntimeError, match="response_model"):

        @router.get("/untyped")
        async def untyped_route():  # type: ignore[no-untyped-def]
            return {"detail": "nope"}


def test_rate_limit_kicks_in_via_memory_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # unreachable -> fallback
    get_settings.cache_clear()

    router = SecureRouter()

    @router.get("/limited", public=True)
    async def limited_route() -> Message:
        return Message(detail="ok")

    client = make_client(router)
    assert client.get("/limited").status_code == 200
    assert client.get("/limited").status_code == 200
    assert client.get("/limited").status_code == 429


def test_client_ip_ignores_forwarded_header_by_default() -> None:
    """trust_forwarded_for defaults off: a caller hitting the API directly
    cannot spoof X-Forwarded-For to dodge rate limiting."""
    router = SecureRouter()

    @router.get("/whoami", public=True)
    async def whoami(request: Request) -> Message:
        return Message(detail=client_ip(request))

    client = make_client(router)
    response = client.get("/whoami", headers={"x-forwarded-for": "9.9.9.9"})
    assert response.json()["detail"] != "9.9.9.9"


def test_client_ip_takes_first_forwarded_entry_when_trusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRUST_FORWARDED_FOR", "true")
    get_settings.cache_clear()

    router = SecureRouter()

    @router.get("/whoami", public=True)
    async def whoami(request: Request) -> Message:
        return Message(detail=client_ip(request))

    client = make_client(router)
    response = client.get("/whoami", headers={"x-forwarded-for": "10.0.0.1, 10.0.0.2"})
    assert response.json()["detail"] == "10.0.0.1"


def test_rate_limit_separates_forwarded_clients_when_trust_is_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression this closes: relay-fronted routes previously keyed the
    bucket on request.client.host, which is always the relay's own address.
    With trust_forwarded_for on, distinct forwarded visitors must not share
    one bucket - two visitors making one request each must not 429 the
    second one just because they share a socket-level client."""
    monkeypatch.setenv("TRUST_FORWARDED_FOR", "true")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # unreachable -> fallback
    get_settings.cache_clear()

    router = SecureRouter()

    @router.get("/limited", public=True)
    async def limited_route() -> Message:
        return Message(detail="ok")

    client = make_client(router)
    response_a = client.get("/limited", headers={"x-forwarded-for": "10.0.0.1"})
    response_b = client.get("/limited", headers={"x-forwarded-for": "10.0.0.2"})
    assert response_a.status_code == 200
    assert response_b.status_code == 200  # distinct forwarded client, distinct bucket

    # a second hit from the same forwarded client still hits its own limit
    response_a_again = client.get("/limited", headers={"x-forwarded-for": "10.0.0.1"})
    assert response_a_again.status_code == 429


def test_rate_limit_shares_bucket_across_forwarded_clients_when_untrusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same scenario with trust_forwarded_for off (the default): both
    forwarded visitors collapse onto the shared TestClient socket address,
    so the second request 429s even though it claims a different XFF - this
    is the byte-for-byte-unchanged default posture."""
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # unreachable -> fallback
    get_settings.cache_clear()

    router = SecureRouter()

    @router.get("/limited", public=True)
    async def limited_route() -> Message:
        return Message(detail="ok")

    client = make_client(router)
    response_a = client.get("/limited", headers={"x-forwarded-for": "10.0.0.1"})
    response_b = client.get("/limited", headers={"x-forwarded-for": "10.0.0.2"})
    assert response_a.status_code == 200
    assert response_b.status_code == 429
