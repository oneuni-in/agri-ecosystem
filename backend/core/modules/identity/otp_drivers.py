"""SMS driver interface + MockDriver / MSG91Driver (D07.D).

The mock is the default everywhere until DLT registration clears
(settings.sms_provider flag); get_sms_driver() is the only selection point, so
the vendor driver is unreachable unless the flag is flipped. Codes never pass
through the logging pipeline - it redacts OTP-shaped numbers by design
(shared/telemetry.py) - so the mock hands codes to tests via an in-memory
outbox and, in dev only, writes them straight to stdout.
"""

import sys
from typing import ClassVar, Protocol

import httpx

from settings import Settings, get_settings
from shared.metrics import OTP_SEND_COST
from shared.telemetry import get_logger

logger = get_logger(__name__)

MSG91_SEND_URL = "https://control.msg91.com/api/v5/flow/"
# DLT transactional-rate ballpark; reconcile against the vendor invoice (the
# counter exists so a flooding attack shows up as money, not just QPS)
MSG91_COST_PER_SMS_INR = 0.25


class SmsDriver(Protocol):
    async def send_otp(self, phone: str, code: str, purpose: str) -> None: ...


class MockDriver:
    """Dev/test driver: no network, codes land in an in-memory outbox."""

    outbox: ClassVar[list[tuple[str, str, str]]] = []

    async def send_otp(self, phone: str, code: str, purpose: str) -> None:
        MockDriver.outbox.append((phone, code, purpose))
        if get_settings().app_env == "dev":
            # stdout on purpose, NOT the logger: the log pipeline redacts
            # 6-digit codes, and dev needs the code to log in
            sys.stdout.write(f"[mock-sms] to={phone} purpose={purpose} code={code}\n")
        logger.info("mock sms queued", extra={"extra_fields": {"purpose": purpose}})

    @classmethod
    def last_code(cls, phone: str) -> str | None:
        """Test inbox: most recent code sent to this phone, if any."""
        for sent_phone, code, _purpose in reversed(cls.outbox):
            if sent_phone == phone:
                return code
        return None

    @classmethod
    def reset(cls) -> None:
        cls.outbox.clear()


class MSG91Driver:
    """Vendor driver: MSG91 flow API with per-purpose DLT template slots.

    Tests exercise it through an injected httpx transport only - a vendor call
    from the test suite is a spec violation (and a real SMS bill).
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    @staticmethod
    def _template_id(settings: Settings, purpose: str) -> str:
        slots = {
            "login": settings.msg91_template_login,
            "verify_email": settings.msg91_template_verify_email,
            "sensitive_action": settings.msg91_template_sensitive_action,
        }
        template_id = slots[purpose]
        if not template_id:
            raise RuntimeError(f"MSG91 DLT template id for purpose {purpose!r} is not configured")
        return template_id

    async def send_otp(self, phone: str, code: str, purpose: str) -> None:
        settings = get_settings()
        payload = {
            "template_id": self._template_id(settings, purpose),
            "sender": settings.msg91_sender_id,
            "mobiles": phone.removeprefix("+"),
            "otp": code,
        }
        async with httpx.AsyncClient(transport=self._transport, timeout=5.0) as client:
            response = await client.post(
                MSG91_SEND_URL, json=payload, headers={"authkey": settings.msg91_auth_key}
            )
        response.raise_for_status()
        OTP_SEND_COST.labels("msg91").inc(MSG91_COST_PER_SMS_INR)
        logger.info(
            "msg91 sms sent",
            extra={"extra_fields": {"purpose": purpose, "cost_inr": MSG91_COST_PER_SMS_INR}},
        )


def get_sms_driver() -> SmsDriver:
    """The single driver selection point, keyed on the settings flag."""
    if get_settings().sms_provider == "msg91":
        return MSG91Driver()
    return MockDriver()
