# backend/core/modules/billing/router.py
"""Billing routes (D20) - the money path. 🔍 human line review required.

EVERYTHING here is gated by the billing_enabled DB flag at request time
(404 while dark - the flag flips without a deploy, unlike the env-mounted
MSG91 webhook). The webhook is public by design: Razorpay cannot log in.
Its gate is the HMAC signature over the raw body + event-id dedupe
(replay = one effect). Bodies are never logged."""

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.billing.models import PaymentEvent
from modules.billing.sanitize import scrub_payload
from modules.billing.service import process_webhook_event, publish_pending
from settings import get_settings
from shared.db import get_session
from shared.flags import flag_enabled
from shared.metrics import BILLING_WEBHOOK_REJECTED
from shared.security import SecureRouter
from shared.telemetry import get_logger

logger = get_logger(__name__)

router = SecureRouter(prefix="/billing", tags=["billing"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _require_flag(session: AsyncSession) -> None:
    """flag off -> this surface does not exist (404, never 403)."""
    if not await flag_enabled("billing_enabled", session=session):
        raise HTTPException(status_code=404, detail="Not Found")


def _principal_user_id(request: Request) -> uuid.UUID:
    principal = request.state.principal  # set by require_auth (shared.security)
    return uuid.UUID(str(principal.user_id))


@router.post("/webhook/razorpay", public=True)
async def razorpay_webhook(request: Request, session: SessionDep) -> dict[str, str]:
    await _require_flag(session)
    body = await request.body()
    secret = get_settings().razorpay_webhook_secret
    signature = request.headers.get("x-razorpay-signature", "")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not secret or not signature or not hmac.compare_digest(expected, signature):
        BILLING_WEBHOOK_REJECTED.labels(reason="signature").inc()
        raise HTTPException(status_code=400, detail="invalid signature")

    event_id = request.headers.get("x-razorpay-event-id", "")
    if not event_id:
        BILLING_WEBHOOK_REJECTED.labels(reason="missing_event_id").inc()
        raise HTTPException(status_code=400, detail="missing event id")
    duplicate = await session.scalar(
        select(PaymentEvent.id).where(PaymentEvent.provider_event_id == event_id)
    )
    if duplicate is not None:
        return {"status": "duplicate"}  # replay: one effect (unique index backstops races)

    try:
        payload = json.loads(body)
    except ValueError as exc:
        BILLING_WEBHOOK_REJECTED.labels(reason="malformed").inc()
        raise HTTPException(status_code=400, detail="malformed body") from exc
    if not isinstance(payload, dict):
        BILLING_WEBHOOK_REJECTED.labels(reason="malformed").inc()
        raise HTTPException(status_code=400, detail="malformed body")

    event_type = str(payload.get("event") or "")
    outcome, pending = await process_webhook_event(
        session,
        event_type=event_type,
        payload=payload,
        now=datetime.now(UTC),
        settings=get_settings(),
    )
    session.add(
        PaymentEvent(
            provider_event_id=event_id,
            event_type=event_type,
            payload=scrub_payload(payload),
            outcome=outcome,
        )
    )
    # capture happened inside process_webhook_event; commit, then best-effort
    # publish (D16 choreography).
    await session.commit()
    await publish_pending(pending)
    return {"status": "ok"}
