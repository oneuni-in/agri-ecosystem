"""MSG91 delivery webhook (D07.D): absent under the default mock driver, and
signature-checked (HMAC-SHA256 over the raw body) when the flag is flipped."""

import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient

from main import create_app
from settings import get_settings

WEBHOOK_PATH = "/auth/otp/webhook/msg91"
SECRET = "webhook-test-secret"


def sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def msg91_app_client(monkeypatch: pytest.MonkeyPatch, secret: str = SECRET) -> TestClient:
    monkeypatch.setenv("SMS_PROVIDER", "msg91")
    monkeypatch.setenv("MSG91_WEBHOOK_SECRET", secret)
    get_settings.cache_clear()
    return TestClient(create_app())


def test_webhook_absent_under_mock_driver() -> None:
    # default build: the route must not exist at all, keeping the public
    # surface exactly the two routes declared in public_routes.txt
    response = TestClient(create_app()).post(WEBHOOK_PATH, content=b"{}")
    assert response.status_code == 404


def test_webhook_route_is_public_when_msg91_active(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMS_PROVIDER", "msg91")
    get_settings.cache_clear()
    assert WEBHOOK_PATH in create_app().state.public_routes


def test_webhook_rejects_missing_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    client = msg91_app_client(monkeypatch)
    assert client.post(WEBHOOK_PATH, content=b'{"status":"DELIVERED"}').status_code == 401


def test_webhook_rejects_bad_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    client = msg91_app_client(monkeypatch)
    body = b'{"status":"DELIVERED"}'
    response = client.post(
        WEBHOOK_PATH, content=body, headers={"x-msg91-signature": sign(body, "wrong-secret")}
    )
    assert response.status_code == 401


def test_webhook_rejects_signature_over_different_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = msg91_app_client(monkeypatch)
    response = client.post(
        WEBHOOK_PATH,
        content=b'{"status":"FAILED"}',
        headers={"x-msg91-signature": sign(b'{"status":"DELIVERED"}')},
    )
    assert response.status_code == 401


def test_webhook_fails_closed_without_configured_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = msg91_app_client(monkeypatch, secret="")
    body = b'{"status":"DELIVERED"}'
    response = client.post(
        WEBHOOK_PATH, content=body, headers={"x-msg91-signature": sign(body, "")}
    )
    assert response.status_code == 401


def test_webhook_accepts_valid_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    client = msg91_app_client(monkeypatch)
    body = b'{"status":"DELIVERED","requestId":"r1"}'
    response = client.post(WEBHOOK_PATH, content=body, headers={"x-msg91-signature": sign(body)})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
