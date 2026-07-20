"""Coins event worker (D13/D16) - standalone consumer of the identity and
directory streams that turns identity lifecycle and directory events into
rules-gated AgriCoins awards.

AgriCoins are NOT money: no purchase, cash-out, or transfer path exists.
Every award routes through modules.coins.service.award (the rules engine),
never a direct ledger write. Awards use deterministic idempotency keys
(modules.coins.rules.deterministic_key) - or, for business_claim, a literal
business-scoped key `claim:{business_id}` built here - so redeliveries of
the same event are always safe - a replayed user.registered or
profile.completed event credits the user at most once.

Run: python -m modules.coins.worker
Never log event payloads (they may carry balance-adjacent or PII fields).
"""

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins import referrals, rules, service
from modules.coins.rules import CapExceededError
from shared.db import get_sessionmaker
from shared.events import Event, EventConsumer
from shared.telemetry import get_logger

logger = get_logger(__name__)

STREAMS = ("identity", "directory")
GROUP = "coins"
NAME = "coins-worker-1"


async def handle_event(session: AsyncSession, event: Event, *, now: datetime) -> None:
    """Pure-ish dispatcher: one identity event in, zero or more awards out.

    Testable without Redis - callers pass an Event built directly.
    """
    if event.type == "user.registered":
        uid = uuid.UUID(event.payload["user_id"])
        await service.award(
            session,
            user_id=uid,
            rule_code="signup_complete",
            ref_id="signup_complete",
            idempotency_key=rules.deterministic_key("signup_complete", uid),
            now=now,
        )
        code = event.payload.get("referral_code")
        if code:
            await referrals.attribute(
                session,
                referee_id=uid,
                code=code,
                device_fingerprint=None,
                phone_prefix=event.payload.get("phone_prefix"),
            )
    elif event.type == "profile.completed":
        uid = uuid.UUID(event.payload["user_id"])
        await service.award(
            session,
            user_id=uid,
            rule_code="profile_100",
            ref_id="profile_100",
            idempotency_key=rules.deterministic_key("profile_100", uid),
            now=now,
        )
        await referrals.maybe_reward(session, referee_id=uid, now=now)
    elif event.type == "identity.session_resumed":
        uid = uuid.UUID(event.payload["user_id"])
        day = now.strftime("%Y-%m-%d")
        await service.award(
            session,
            user_id=uid,
            rule_code="daily_visit",
            ref_id=day,
            idempotency_key=rules.deterministic_key("daily_visit", uid, day=day),
            now=now,
        )
    elif event.type == "business.claimed":
        uid = uuid.UUID(event.payload["user_id"])
        business_id = str(event.payload["business_id"])
        await service.award(
            session,
            user_id=uid,
            rule_code="business_claim",
            ref_id=business_id,
            # D16 spec: once per BUSINESS ever - business-scoped key, built
            # here because rules.deterministic_key's branches are user- or
            # ref-code-scoped, not this literal shape.
            idempotency_key=f"claim:{business_id}",
            now=now,
        )
    elif event.type == "review.approved":
        # review_approved: idem key review:{review_id} (spec) makes replay
        # safe; the 5/week cap is data (coins.rules.weekly_cap=5) enforced by
        # check_numeric_caps inside award() - cap-hit is a normal outcome,
        # not a retryable fault, so it must not poison the stream.
        uid = uuid.UUID(str(event.payload["user_id"]))
        review_id = str(event.payload["review_id"])
        try:
            await service.award(
                session,
                user_id=uid,
                rule_code="review_approved",
                ref_id=review_id,
                idempotency_key=f"review:{review_id}",
                now=now,
            )
        except CapExceededError:
            logger.info(
                "review_approved weekly cap reached",
                extra={"extra_fields": {"user_id": str(uid)}},
            )
    # unknown event types: no-op (other consumers own them)


async def run() -> None:  # pragma: no cover - exercised via integration, not unit
    consumers = [EventConsumer(stream, group=GROUP, name=NAME) for stream in STREAMS]
    for consumer in consumers:
        await consumer.ensure_group()
    logger.info(
        "coins worker started",
        extra={"extra_fields": {"streams": list(STREAMS), "group": GROUP}},
    )
    maker = get_sessionmaker()
    while True:
        # KNOWN BUS LIMITATION (D12): EventConsumer has no idle-redelivery /
        # XAUTOCLAIM sweep of its own pending entries, so an event that is
        # left unacked below (the Exception branch) is not currently re-read
        # by this loop or DLQ'd until reap_poison's delivery-count check
        # catches up on a later read. Do NOT try to fix the bus here - all
        # awards are idempotent (deterministic keys + UNIQUE constraint), so
        # the at-least-once/at-most-once quirks this creates cannot corrupt a
        # balance; the worst case is a delayed award, not a wrong one.
        idle = True
        for consumer in consumers:
            await consumer.reap_poison()
            events = await consumer.read(count=50)
            if events:
                idle = False
            for event in events:
                try:
                    async with maker() as session:
                        await handle_event(session, event, now=datetime.now(UTC))
                        await session.commit()
                    await consumer.ack(event)
                except service.InsufficientBalanceError:
                    await consumer.ack(event)  # nothing to retry; not an error
                except Exception:
                    logger.exception(
                        "coins worker: event failed; leaving for redelivery/DLQ",
                        extra={"extra_fields": {"event_type": event.type}},
                    )
                    # no ack -> eligible for redelivery; poison after
                    # MAX_DELIVERIES -> DLQ via reap_poison above
        if idle:
            await asyncio.sleep(0.5)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(run())
