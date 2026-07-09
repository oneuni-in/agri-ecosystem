"""The Constitution's core guarantee: a thoughtlessly-added route is private
and rate-limited. THE test: no public=True -> 401."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from settings import get_settings
from shared.security import SecureRouter


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
