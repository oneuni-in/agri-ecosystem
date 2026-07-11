"""SMS drivers (D07.D): mock is the default and the vendor driver is
unreachable unless the settings flag flips; MSG91 requests are exercised
through an injected transport - the suite never touches the network."""

import json

import httpx
import pytest

from modules.identity.otp_drivers import (
    MSG91_COST_PER_SMS_INR,
    MockDriver,
    MSG91Driver,
    get_sms_driver,
)
from settings import get_settings
from shared.metrics import registry


def _use_msg91(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMS_PROVIDER", "msg91")
    monkeypatch.setenv("MSG91_AUTH_KEY", "test-auth-key")
    monkeypatch.setenv("MSG91_SENDER_ID", "AGRIID")
    monkeypatch.setenv("MSG91_TEMPLATE_LOGIN", "dlt-template-login")
    get_settings.cache_clear()


def test_mock_driver_is_the_default() -> None:
    assert get_settings().sms_provider == "mock"
    assert isinstance(get_sms_driver(), MockDriver)


def test_flag_flip_selects_msg91(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_msg91(monkeypatch)
    assert isinstance(get_sms_driver(), MSG91Driver)


async def test_mock_outbox_exposes_last_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    driver = MockDriver()
    await driver.send_otp("+919876543210", "111111", "login")
    await driver.send_otp("+919876543210", "222222", "login")
    await driver.send_otp("+919876543211", "333333", "verify_email")
    assert MockDriver.last_code("+919876543210") == "222222"
    assert MockDriver.last_code("+919876543211") == "333333"
    assert MockDriver.last_code("+919876543299") is None


async def test_mock_writes_code_to_stdout_in_dev_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    get_settings.cache_clear()
    await MockDriver().send_otp("+919876543210", "424242", "login")
    assert "424242" in capsys.readouterr().out

    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    await MockDriver().send_otp("+919876543210", "535353", "login")
    assert "535353" not in capsys.readouterr().out


async def test_msg91_sends_dlt_template_request(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_msg91(monkeypatch)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"type": "success"})

    driver = MSG91Driver(transport=httpx.MockTransport(handler))
    await driver.send_otp("+919876543210", "654321", "login")

    assert len(seen) == 1
    request = seen[0]
    assert request.headers["authkey"] == "test-auth-key"
    body = json.loads(request.content)
    assert body == {
        "template_id": "dlt-template-login",
        "sender": "AGRIID",
        "mobiles": "919876543210",  # MSG91 wants no leading +
        "otp": "654321",
    }


async def test_msg91_logs_send_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_msg91(monkeypatch)
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"type": "success"}))
    await MSG91Driver(transport=transport).send_otp("+919876543210", "654321", "login")
    cost = registry.get_sample_value("otp_send_cost_inr_total", {"provider": "msg91"})
    assert cost == MSG91_COST_PER_SMS_INR


async def test_msg91_missing_template_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_msg91(monkeypatch)
    transport = httpx.MockTransport(lambda _: httpx.Response(200))
    with pytest.raises(RuntimeError, match="verify_email"):
        await MSG91Driver(transport=transport).send_otp("+919876543210", "1", "verify_email")


async def test_msg91_vendor_error_bubbles(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_msg91(monkeypatch)
    transport = httpx.MockTransport(lambda _: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await MSG91Driver(transport=transport).send_otp("+919876543210", "654321", "login")
