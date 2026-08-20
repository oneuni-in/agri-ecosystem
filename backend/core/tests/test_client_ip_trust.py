# backend/core/tests/test_client_ip_trust.py
"""A caller may not nominate its own client IP.

`trust_forwarded_for` has to be on in production - modules/directory/
analytics.py says so, and D19 location needs it - because every browser
request reaches the API through a Next relay, so the socket address is always
the relay's. The old implementation read X-Forwarded-For from *anyone* once
that flag was on.

That is exploitable, because X-Forwarded-For is not a forbidden header name:
page JavaScript can set it on a same-origin fetch, and the relays copied it
through verbatim. Whoever asked got to pick the value that keys the rate
limiter (`ratelimit:{client_ip}:{path}`) and seeds the daily viewer pseudonym
(directory/analytics.viewer_hash). An edge proxy does not save this either -
Cloudflare APPENDS to a client-supplied X-Forwarded-For rather than replacing
it, and the old code took `.split(",")[0]`, which is the attacker's entry.

So the header is only believed when the immediate peer is a relay the
operator has declared in `trusted_proxy_ips`. Undeclared peer, or no
declaration at all, and the socket address wins: visitors collapse into one
bucket, which is a throughput limit rather than a security hole.
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel

from settings import get_settings
from shared.security import SecureRouter, client_ip

RELAY = "10.9.0.1"
VISITOR = "203.0.113.9"


class Message(BaseModel):
    detail: str


def make_client(peer: str) -> TestClient:
    """TestClient whose socket address is `peer` (default is 'testclient')."""
    router = SecureRouter()

    @router.get("/whoami", public=True)
    async def whoami(request: Request) -> Message:
        return Message(detail=client_ip(request))

    app = FastAPI()
    app.include_router(router)
    return TestClient(app, client=(peer, 50000))


def _trust(monkeypatch: pytest.MonkeyPatch, *, relays: str | None = None) -> None:
    monkeypatch.setenv("TRUST_FORWARDED_FOR", "true")
    if relays is not None:
        monkeypatch.setenv("TRUSTED_PROXY_IPS", relays)
    get_settings.cache_clear()


def test_forwarded_header_from_undeclared_peer_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE fix. Trust is on, but nobody declared this caller a relay."""
    _trust(monkeypatch)
    response = make_client(VISITOR).get("/whoami", headers={"x-forwarded-for": "1.2.3.4"})
    assert response.json()["detail"] == VISITOR


def test_forwarded_header_from_a_declared_relay_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _trust(monkeypatch, relays=RELAY)
    response = make_client(RELAY).get("/whoami", headers={"x-forwarded-for": "1.2.3.4"})
    assert response.json()["detail"] == "1.2.3.4"


def test_a_relay_may_be_declared_as_a_cidr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Compose assigns container addresses out of a subnet, so pinning single
    addresses would not survive a redeploy."""
    _trust(monkeypatch, relays="172.16.0.0/12")
    response = make_client("172.18.0.7").get("/whoami", headers={"x-forwarded-for": "1.2.3.4"})
    assert response.json()["detail"] == "1.2.3.4"


def test_peer_outside_the_declared_cidr_is_still_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _trust(monkeypatch, relays="172.16.0.0/12")
    response = make_client(VISITOR).get("/whoami", headers={"x-forwarded-for": "1.2.3.4"})
    assert response.json()["detail"] == VISITOR


def test_a_forwarded_value_that_is_not_an_address_falls_back_to_the_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even behind a trusted relay the value originates further out. A
    non-address would otherwise become a rate-limit key an attacker picks."""
    _trust(monkeypatch, relays=RELAY)
    response = make_client(RELAY).get("/whoami", headers={"x-forwarded-for": "not-an-ip"})
    assert response.json()["detail"] == RELAY


def test_a_malformed_relay_declaration_does_not_trust_everyone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo in the setting must fail closed, not open."""
    _trust(monkeypatch, relays="nonsense, ,also-nonsense")
    response = make_client(VISITOR).get("/whoami", headers={"x-forwarded-for": "1.2.3.4"})
    assert response.json()["detail"] == VISITOR


def test_spoofed_headers_cannot_split_the_rate_limit_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reason this matters: the limiter keys on client_ip, so if a caller
    can nominate it, the limit is advisory. One undeclared caller rotating the
    header must still exhaust a single bucket."""
    _trust(monkeypatch)
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # unreachable -> in-memory
    get_settings.cache_clear()

    client = make_client(VISITOR)
    assert client.get("/whoami", headers={"x-forwarded-for": "1.1.1.1"}).status_code == 200
    assert client.get("/whoami", headers={"x-forwarded-for": "2.2.2.2"}).status_code == 429
