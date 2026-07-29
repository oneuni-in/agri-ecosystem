"""Identity module routes (D07.E): OTP request/verify + flag-gated MSG91 webhook.

/auth/otp/request and /auth/otp/verify are the module's only public routes and
are declared in backend/core/public_routes.txt. Both answer identically for
registered and unknown phones (enumeration resistance); verify returns a
single-use otp_proof for the D08/D09 login flow, never a session.

The MSG91 delivery webhook is built here but mounted by main.create_app() ONLY
when settings.sms_provider == "msg91" - the default (mock) app must expose
exactly the two routes above, and flipping the flag forces a public_routes.txt
edit where a reviewer sees the new exposure.
"""

import hashlib
import hmac
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.otp_limits import OTP_PROOF_TTL_SECONDS
from modules.identity.otp_service import (
    OtpPurpose,
    OtpVerifyError,
    issue_otp,
    verify_otp,
)
from modules.identity.otp_throttle import OtpRateLimited
from modules.identity.phone import normalize_phone
from modules.identity.signup_gate import signup_allowed
from settings import get_settings
from shared.db import get_session
from shared.security import SecureRouter
from shared.telemetry import get_logger

logger = get_logger(__name__)

router = SecureRouter(prefix="/identity", tags=["identity"])

otp_router = SecureRouter(prefix="/auth/otp", tags=["auth-otp"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

MSG91_SIGNATURE_HEADER = "x-msg91-signature"


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


class _PhoneModel(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def _normalize(cls, value: str) -> str:
        # PhoneError -> ValueError -> 422; format check only, no registry
        # lookup, so the response cannot leak whether the phone is known
        return normalize_phone(value)


class OtpRequestIn(_PhoneModel):
    purpose: OtpPurpose
    device_fingerprint: str | None = None


class OtpRequestOut(BaseModel):
    status: Literal["sent"] = "sent"


class OtpVerifyIn(_PhoneModel):
    purpose: OtpPurpose
    code: str


class OtpVerifyOut(BaseModel):
    otp_proof: str
    expires_in: int


def _rate_limited(exc: OtpRateLimited) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail="rate_limited",
        headers={"Retry-After": str(exc.retry_after)},
    )


@otp_router.post("/request", public=True)
async def request_otp(body: OtpRequestIn, request: Request, session: SessionDep) -> OtpRequestOut:
    """Issue a code. The 200 body is identical for known and unknown phones."""
    if not await signup_allowed(session=session):
        # 503, not 403: this is "temporarily unavailable", and must not read as
        # an auth failure to a client or an uptime monitor. The detail string is
        # a contract - web-id renders the "login coming shortly" notice off it
        # rather than a generic error (D30.B).
        raise HTTPException(status_code=503, detail="signup_unavailable")
    try:
        await issue_otp(
            session,
            phone=body.phone,
            purpose=body.purpose,
            ip=_client_ip(request),
            device_fingerprint=body.device_fingerprint,
        )
    except OtpRateLimited as exc:
        raise _rate_limited(exc) from exc
    return OtpRequestOut()


@otp_router.post("/verify", public=True)
async def verify_otp_route(
    body: OtpVerifyIn, request: Request, session: SessionDep
) -> OtpVerifyOut:
    """Redeem a code for a short-lived otp_proof. Every failure mode returns
    the same 400 body - wrong, expired, burned, and never-issued are
    indistinguishable to the caller."""
    try:
        proof = await verify_otp(
            session,
            phone=body.phone,
            purpose=body.purpose,
            code=body.code,
            ip=_client_ip(request),
        )
    except OtpRateLimited as exc:
        raise _rate_limited(exc) from exc
    except OtpVerifyError as exc:
        # commit BEFORE raising: the 400 must not roll back the attempt
        # counter/burn, or brute-force attempts would never accumulate
        # (an exception skips get_session's commit)
        await session.commit()
        raise HTTPException(status_code=400, detail="invalid_or_expired_code") from exc
    return OtpVerifyOut(otp_proof=proof, expires_in=OTP_PROOF_TTL_SECONDS)


class DeliveryAck(BaseModel):
    status: Literal["ok"] = "ok"


def msg91_webhook_router() -> SecureRouter:
    """Delivery-status webhook, mounted only when sms_provider == "msg91".

    Its auth is the HMAC signature over the raw body, checked in-handler;
    activating it in an environment requires declaring the route in
    public_routes.txt in that same change."""
    webhook = SecureRouter(prefix="/auth/otp", tags=["auth-otp"])

    @webhook.post("/webhook/msg91", public=True)
    async def msg91_delivery_status(request: Request) -> DeliveryAck:
        raw = await request.body()
        secret = get_settings().msg91_webhook_secret
        supplied = request.headers.get(MSG91_SIGNATURE_HEADER, "")
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not secret or not hmac.compare_digest(expected, supplied):
            raise HTTPException(status_code=401, detail="invalid signature")
        # bodies are vendor delivery reports; log the status only, never the
        # payload (it contains phone numbers)
        logger.info("msg91 delivery status received")
        return DeliveryAck()

    return webhook


class OtpPeekOut(BaseModel):
    code: str | None


class OtpResetOut(BaseModel):
    status: Literal["ok"] = "ok"


def otp_test_peek_router() -> SecureRouter:
    """E2E peek at the mock outbox, mounted by main.create_app() ONLY when
    settings.otp_test_peek is set outside prod. Same doctrine as the msg91
    webhook: default builds expose exactly the public_routes.txt surface."""
    from modules.identity.otp_drivers import MockDriver
    from shared.cache import get_redis

    peek = SecureRouter(prefix="/auth/otp", tags=["auth-otp"])

    @peek.get("/_peek", public=True)
    async def otp_peek(phone: str) -> OtpPeekOut:
        return OtpPeekOut(code=MockDriver.last_code(normalize_phone(phone)))

    @peek.post("/_reset", public=True)
    async def otp_reset(body: _PhoneModel, request: Request) -> OtpResetOut:
        """Clear the D07 throttle ladder for one phone + the caller's IP so
        E2E scenarios can log the same phone in twice without a 30s wait."""
        ip = _client_ip(request)
        keys = [
            f"otp:cd:{body.phone}",
            f"otp:cdlvl:{body.phone}",
            f"otp:day:phone:{body.phone}",
        ]
        if ip:
            keys += [f"otp:day:ip:{ip}", f"otp:vday:ip:{ip}", f"otp:phones:{ip}"]
        await get_redis().delete(*keys)
        return OtpResetOut()

    return peek
