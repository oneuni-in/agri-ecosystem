"""Notify channel drivers (D12): mock SMS + mock/ZeptoMail email.

get_*_driver() are the ONLY selection points, mirroring identity's
otp_drivers pattern. An import-linter forbidden contract keeps every other
module away from this file: sends go through the notify engine (preferences,
rate cap, flag) or not at all. Destinations and bodies are never logged."""

from typing import ClassVar, Protocol

import httpx

from settings import get_settings
from shared.telemetry import get_logger

logger = get_logger(__name__)

ZEPTOMAIL_SEND_URL = "https://api.zeptomail.in/v1.1/email"


class EmailDriver(Protocol):
    async def send(self, to: str, subject: str, body: str) -> str | None: ...


class NotifySmsDriver(Protocol):
    async def send(self, phone: str, body: str) -> str | None: ...


class MockEmailDriver:
    """Dev/test: mails land in an inspectable in-memory outbox."""

    outbox: ClassVar[list[tuple[str, str, str]]] = []

    async def send(self, to: str, subject: str, body: str) -> str | None:
        MockEmailDriver.outbox.append((to, subject, body))
        logger.info("mock email queued", extra={"extra_fields": {"subject_len": len(subject)}})
        return None

    @classmethod
    def reset(cls) -> None:
        cls.outbox.clear()


class MockNotifySmsDriver:
    """Dev/test: SMS lands in an inspectable in-memory outbox. The real
    transactional-SMS adapter arrives when DLT templates for notify clear;
    identity's OTP driver is purpose-specific and stays in identity."""

    outbox: ClassVar[list[tuple[str, str]]] = []

    async def send(self, phone: str, body: str) -> str | None:
        MockNotifySmsDriver.outbox.append((phone, body))
        logger.info("mock notify sms queued", extra={"extra_fields": {"body_len": len(body)}})
        return None

    @classmethod
    def reset(cls) -> None:
        cls.outbox.clear()


class ZeptoMailDriver:
    """Zoho ZeptoMail transactional API. Tests use an injected transport only."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def send(self, to: str, subject: str, body: str) -> str | None:
        settings = get_settings()
        payload = {
            "from": {"address": settings.zeptomail_from},
            "to": [{"email_address": {"address": to}}],
            "subject": subject,
            "htmlbody": body,
        }
        async with httpx.AsyncClient(transport=self._transport, timeout=10.0) as client:
            response = await client.post(
                ZEPTOMAIL_SEND_URL,
                json=payload,
                headers={"authorization": f"Zoho-enczapikey {settings.zeptomail_token}"},
            )
        response.raise_for_status()
        data = response.json()
        request_id = data.get("request_id")
        logger.info("zeptomail sent", extra={"extra_fields": {"request_id": request_id}})
        return str(request_id) if request_id is not None else None


def get_email_driver() -> EmailDriver:
    if get_settings().email_provider == "zeptomail":
        return ZeptoMailDriver()
    return MockEmailDriver()


def get_notify_sms_driver() -> NotifySmsDriver:
    return MockNotifySmsDriver()
