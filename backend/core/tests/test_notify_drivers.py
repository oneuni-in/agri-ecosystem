"""D12 drivers: mock outboxes for tests/dev; ZeptoMail exercised only through
an injected httpx transport (a vendor call from tests is a spec violation)."""

import httpx
import pytest

from modules.notify.drivers import (
    MockEmailDriver,
    MockNotifySmsDriver,
    ZeptoMailDriver,
    get_email_driver,
    get_notify_sms_driver,
)
from settings import get_settings


async def test_mock_email_lands_in_outbox() -> None:
    ref = await MockEmailDriver().send("farmer@example.com", "Hi", "Body")
    assert MockEmailDriver.outbox == [("farmer@example.com", "Hi", "Body")]
    assert ref is None


async def test_mock_sms_lands_in_outbox() -> None:
    await MockNotifySmsDriver().send("+919876500001", "Body")
    assert MockNotifySmsDriver.outbox == [("+919876500001", "Body")]


def test_default_selection_is_mock() -> None:
    assert isinstance(get_email_driver(), MockEmailDriver)
    assert isinstance(get_notify_sms_driver(), MockNotifySmsDriver)


async def test_zeptomail_posts_and_returns_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZEPTOMAIL_TOKEN", "test-token")
    get_settings.cache_clear()
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(201, json={"request_id": "zepto-123"})

    driver = ZeptoMailDriver(transport=httpx.MockTransport(handler))
    ref = await driver.send("farmer@example.com", "Hi", "Body")
    assert ref == "zepto-123"
    assert seen["url"] == "https://api.zeptomail.in/v1.1/email"
    assert seen["auth"] == "Zoho-enczapikey test-token"


async def test_zeptomail_raises_on_http_error() -> None:
    driver = ZeptoMailDriver(
        transport=httpx.MockTransport(lambda request: httpx.Response(500, json={}))
    )
    with pytest.raises(httpx.HTTPStatusError):
        await driver.send("farmer@example.com", "Hi", "Body")
