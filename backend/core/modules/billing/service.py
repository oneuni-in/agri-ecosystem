"""Billing state machine (D20) - the money path. 🔍 human line review req'd.

Invariants:
- Every transition runs inside the caller's transaction; webhook callers
  lock the subscription row FOR UPDATE before calling in here.
- Notification payloads are captured BEFORE commit and published to the bus
  only AFTER commit (D16 choreography) via publish_pending().
- The clock is always injected (`now`); nothing here calls datetime.now().
- run_due_dunning() re-checks billing_enabled and no-ops while dark.
- Dunning retry offsets are CUMULATIVE from past_due_since; after the last
  offset a grace window (dunning_grace_days) runs, then cancellation.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.billing.models import Invoice, Subscription
from modules.billing.razorpay_client import RazorpayError
from settings import Settings
from shared.events import publish
from shared.flags import flag_enabled
from shared.lookups import resolve_business, resolve_contact
from shared.telemetry import get_logger

logger = get_logger(__name__)

EVENT_STREAM = "billing"
PendingEvent = tuple[str, dict[str, Any]]

# Statuses Razorpay reports that mean "the money keeps flowing" for a local
# `active` row; used by the dunning-tick recovery sync and reconciliation.
REMOTE_ACTIVE = frozenset({"active"})


def dunning_offsets(settings: Settings) -> list[timedelta]:
    hours = [int(part) for part in settings.dunning_retry_hours.split(",") if part.strip()]
    if not hours or hours != sorted(hours) or hours[0] <= 0:
        raise ValueError("dunning_retry_hours must be ascending positive hours, e.g. '24,72,168'")
    return [timedelta(hours=hour) for hour in hours]


async def _pending_notification(
    session: AsyncSession, business_id: uuid.UUID, event_type: str, vars_: dict[str, Any]
) -> PendingEvent | None:
    """Build a self-contained notify payload (D12 contract): destination and
    locale resolved here, used once by the notify consumer, never logged."""
    ref = await resolve_business(session, business_id)
    if ref is None or ref.owner_user_id is None:
        return None  # unowned/claimable business - nobody to notify
    contact = await resolve_contact(session, ref.owner_user_id)
    payload: dict[str, Any] = {
        "user_id": str(ref.owner_user_id),
        "locale": (contact.locale if contact else None) or "en",
        "email": contact.email if contact else None,
        "phone": None,
        "vars": {**vars_, "business_name": ref.name},
    }
    return (event_type, payload)


async def publish_pending(events: Sequence[PendingEvent]) -> None:
    """Best-effort, AFTER commit: a Redis blip must never roll back a money
    transition, and an event for a rolled-back transition must never exist."""
    for event_type, payload in events:
        try:
            await publish(EVENT_STREAM, event_type, payload)
        except Exception as exc:
            logger.warning(
                "billing.event_publish_failed",
                extra={"extra_fields": {"event_type": event_type, "exc_type": type(exc).__name__}},
            )


async def apply_subscription_charged(
    session: AsyncSession,
    sub: Subscription,
    *,
    period_end: datetime | None,
    payment: dict[str, Any],
    now: datetime,
) -> list[PendingEvent]:
    first_charge = sub.current_period_end is None
    was_past_due = sub.status == "past_due"
    sub.status = "active"
    if period_end is not None:
        sub.current_period_end = period_end
    sub.dunning_attempt = 0
    sub.next_retry_at = None
    sub.past_due_since = None

    invoice_id = payment.get("invoice_id")
    if invoice_id:
        invoice = await session.scalar(
            select(Invoice).where(Invoice.razorpay_invoice_id == str(invoice_id))
        )
        if invoice is None:
            session.add(
                Invoice(
                    subscription_id=sub.id,
                    amount_paise=int(payment.get("amount") or 0),
                    status="paid",
                    razorpay_invoice_id=str(invoice_id),
                    period_end=period_end,
                )
            )
        else:
            invoice.status = "paid"
    await session.flush()

    if first_charge or was_past_due:
        pending = await _pending_notification(
            session, sub.business_id, "billing.subscription_activated", {"tier": sub.tier}
        )
        return [pending] if pending else []
    # renewals are silent today (invoice shows in the console); the event
    # still fires for future consumers - notify has no route for it and
    # ignores it by design.
    pending = await _pending_notification(
        session, sub.business_id, "billing.subscription_renewed", {"tier": sub.tier}
    )
    return [pending] if pending else []


async def apply_charge_failed(
    session: AsyncSession, sub: Subscription, *, now: datetime, settings: Settings
) -> list[PendingEvent]:
    if sub.status != "active":
        return []  # already dunning or canceled; Razorpay re-sends pending/halted
    offsets = dunning_offsets(settings)
    sub.status = "past_due"
    sub.past_due_since = now
    sub.dunning_attempt = 0
    sub.next_retry_at = now + offsets[0]
    await session.flush()
    pending = await _pending_notification(
        session, sub.business_id, "billing.payment_failed", {"tier": sub.tier}
    )
    return [pending] if pending else []


async def apply_subscription_cancelled(
    session: AsyncSession, sub: Subscription, *, now: datetime
) -> list[PendingEvent]:
    if sub.status == "canceled":
        return []
    sub.status = "canceled"
    sub.next_retry_at = None
    await session.flush()
    pending = await _pending_notification(
        session, sub.business_id, "billing.subscription_canceled", {"tier": sub.tier}
    )
    return [pending] if pending else []


def _period_end_from_entity(sub_entity: dict[str, Any]) -> datetime | None:
    current_end = sub_entity.get("current_end")
    if not current_end:
        return None
    return datetime.fromtimestamp(int(current_end), UTC)


HANDLED_EVENTS = frozenset(
    {
        "subscription.charged",
        "subscription.pending",
        "subscription.halted",
        "subscription.cancelled",
        "subscription.completed",
        "invoice.paid",
        "invoice.expired",
    }
)


async def process_webhook_event(
    session: AsyncSession,
    *,
    event_type: str,
    payload: dict[str, Any],
    now: datetime,
    settings: Settings,
) -> tuple[str, list[PendingEvent]]:
    """Route one verified, deduped webhook to its transition. Runs in the
    webhook route's transaction; the payment_events row is appended by the
    caller with the outcome returned here."""
    if event_type not in HANDLED_EVENTS:
        return ("ignored", [])
    entity = payload.get("payload") or {}

    if event_type.startswith("invoice."):
        inv_entity = (entity.get("invoice") or {}).get("entity") or {}
        invoice = await session.scalar(
            select(Invoice).where(Invoice.razorpay_invoice_id == str(inv_entity.get("id")))
        )
        if invoice is None:
            return ("unmatched", [])
        invoice.status = "paid" if event_type == "invoice.paid" else "void"
        return ("processed", [])

    sub_entity = (entity.get("subscription") or {}).get("entity") or {}
    payment = (entity.get("payment") or {}).get("entity") or {}
    razorpay_sub_id = sub_entity.get("id") or payment.get("subscription_id")
    if not razorpay_sub_id:
        return ("unmatched", [])
    sub = await session.scalar(
        select(Subscription)
        .where(Subscription.razorpay_sub_id == str(razorpay_sub_id))
        .with_for_update()
    )
    if sub is None:
        return ("unmatched", [])

    if event_type == "subscription.charged":
        pending = await apply_subscription_charged(
            session, sub, period_end=_period_end_from_entity(sub_entity), payment=payment, now=now
        )
    elif event_type in ("subscription.pending", "subscription.halted"):
        pending = await apply_charge_failed(session, sub, now=now, settings=settings)
    else:  # subscription.cancelled / subscription.completed
        pending = await apply_subscription_cancelled(session, sub, now=now)
    return ("processed", pending)


async def run_due_dunning(
    session: AsyncSession, *, now: datetime, client: Any, settings: Settings
) -> tuple[int, list[PendingEvent]]:
    """One dunning tick: advance every due past_due subscription. `client`
    is anything with the RazorpayClient method surface (tests inject
    FakeRazorpay). Caller commits, then publish_pending(pending)."""
    if not await flag_enabled("billing_enabled", session=session):
        return (0, [])
    offsets = dunning_offsets(settings)
    grace = timedelta(days=settings.dunning_grace_days)
    subs = (
        await session.scalars(
            select(Subscription)
            .where(Subscription.status == "past_due", Subscription.next_retry_at <= now)
            .with_for_update(skip_locked=True)
        )
    ).all()
    pending: list[PendingEvent] = []
    for sub in subs:
        remote: dict[str, Any] | None = None
        if sub.razorpay_sub_id:
            try:
                remote = await client.fetch_subscription(sub.razorpay_sub_id)
            except RazorpayError as exc:
                logger.warning(
                    "billing.dunning_sync_failed",
                    extra={
                        "extra_fields": {
                            "subscription_id": str(sub.id),
                            "exc_type": type(exc).__name__,
                        }
                    },
                )
        if remote is not None and remote.get("status") in REMOTE_ACTIVE:
            # Razorpay auto-retried and recovered; we missed the webhook.
            pending.extend(
                await apply_subscription_charged(
                    session,
                    sub,
                    period_end=_period_end_from_entity(remote),
                    payment={},
                    now=now,
                )
            )
            continue
        if sub.dunning_attempt >= len(offsets):
            # grace elapsed - cancel at the provider first, then locally. A
            # provider error skips just this sub; next_retry_at is already in
            # the past, so the next tick retries the cancellation.
            if sub.razorpay_sub_id:
                try:
                    await client.cancel_subscription(sub.razorpay_sub_id)
                except RazorpayError as exc:
                    logger.warning(
                        "billing.dunning_cancel_failed",
                        extra={
                            "extra_fields": {
                                "subscription_id": str(sub.id),
                                "exc_type": type(exc).__name__,
                            }
                        },
                    )
                    continue
            pending.extend(await apply_subscription_cancelled(session, sub, now=now))
            continue
        note = await _pending_notification(
            session,
            sub.business_id,
            "billing.dunning_reminder",
            {"tier": sub.tier, "attempt": sub.dunning_attempt + 1},
        )
        if note is not None:
            pending.append(note)
        sub.dunning_attempt += 1
        base = sub.past_due_since or now
        if sub.dunning_attempt < len(offsets):
            sub.next_retry_at = base + offsets[sub.dunning_attempt]
        else:
            sub.next_retry_at = base + offsets[-1] + grace
    await session.flush()
    return (len(subs), pending)
