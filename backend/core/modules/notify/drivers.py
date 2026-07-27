"""Notify channel drivers (D12/D28): mock SMS + mock/ZeptoMail email +
mock/VAPID web push.

get_*_driver() are the ONLY selection points, mirroring identity's
otp_drivers pattern. An import-linter forbidden contract keeps every other
module away from this file: sends go through the notify engine (preferences,
rate cap, flag) or not at all. Destinations, endpoints and bodies are never
logged."""

import asyncio
import json
from typing import Any, ClassVar, Protocol

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


class ExpiredSubscriptionError(Exception):
    """Provider says this endpoint is gone (404/410): prune, don't retry."""


class PushDriver(Protocol):
    async def send(
        self, subscription_info: dict[str, Any], title: str, body: str
    ) -> str | None: ...


class MockPushDriver:
    """Dev/test: pushes land in an inspectable in-memory outbox."""

    outbox: ClassVar[list[tuple[str, str, str]]] = []  # (endpoint, title, body)

    async def send(self, subscription_info: dict[str, Any], title: str, body: str) -> str | None:
        MockPushDriver.outbox.append((subscription_info["endpoint"], title, body))
        logger.info("mock push queued", extra={"extra_fields": {"title_len": len(title)}})
        return None

    @classmethod
    def reset(cls) -> None:
        cls.outbox.clear()


class WebPushDriver:
    """VAPID web push via pywebpush (sync lib -> to_thread). Endpoint URLs
    are durable device identifiers: never logged (module rule)."""

    async def send(self, subscription_info: dict[str, Any], title: str, body: str) -> str | None:
        from pywebpush import WebPushException, webpush

        settings = get_settings()
        try:
            await asyncio.to_thread(
                webpush,
                subscription_info=subscription_info,
                data=json.dumps({"title": title, "body": body, "url": "/notifications"}),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
                ttl=3600,
            )
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (404, 410):
                raise ExpiredSubscriptionError from exc
            raise
        return None


def get_push_driver() -> PushDriver:
    settings = get_settings()
    if settings.vapid_private_key and settings.vapid_public_key:
        return WebPushDriver()
    return MockPushDriver()


def get_email_driver() -> EmailDriver:
    if get_settings().email_provider == "zeptomail":
        return ZeptoMailDriver()
    return MockEmailDriver()


def get_notify_sms_driver() -> NotifySmsDriver:
    return MockNotifySmsDriver()
