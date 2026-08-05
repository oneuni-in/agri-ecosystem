"""M5 Task 7: the campaign lifecycle engine. The conjunction matrix is the
heart of this suite - a campaign must NEVER activate on payment alone or on
moderation alone; both gates must clear (NON-NEGOTIABLE)."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads import lifecycle
from modules.ads.models import Campaign, Creative

pytestmark = pytest.mark.asyncio

TODAY = date(2026, 8, 5)
FLIGHT_START = TODAY - timedelta(days=1)
FLIGHT_END = TODAY + timedelta(days=14)


def _campaign(**overrides: object) -> Campaign:
    fields: dict[str, object] = {
        "advertiser_business_id": uuid.uuid4(),
        "name": "Kharif push",
        "status": "draft",
        "flight_start": FLIGHT_START,
        "flight_end": FLIGHT_END,
        "price_paise": 100_000,
        "price_subtotal_paise": 90_000,
        "price_gst_paise": 10_000,
        "pricing_model": "cpm",
        "rate_card_version": 1,
        "budget_serves_total": 5000,
    }
    fields.update(overrides)
    return Campaign(**fields)


async def _creative(session: AsyncSession, campaign: Campaign, status: str) -> Creative:
    creative = Creative(
        campaign_id=campaign.id,
        media_keys=["ads/x.jpg"],
        copy={"en": {"title": "t", "body": "b"}},
        target_url="https://example.com",
    )
    session.add(creative)
    await session.flush()
    creative.moderation_status = status
    await session.flush()
    return creative


# ---------------------------------------------------------------------------
# request_checkout


async def test_request_checkout_draft_with_creative_moves_to_pending_payment(
    db_session: AsyncSession,
) -> None:
    campaign = _campaign()
    db_session.add(campaign)
    await db_session.flush()
    await _creative(db_session, campaign, "pending")

    await lifecycle.request_checkout(db_session, campaign)
    assert campaign.status == "pending_payment"


async def test_request_checkout_non_draft_raises_not_payable(db_session: AsyncSession) -> None:
    campaign = _campaign(status="active")
    db_session.add(campaign)
    await db_session.flush()
    await _creative(db_session, campaign, "approved")

    with pytest.raises(lifecycle.LifecycleError) as exc_info:
        await lifecycle.request_checkout(db_session, campaign)
    assert exc_info.value.code == "not_payable"


async def test_request_checkout_unpriced_raises_not_priced(db_session: AsyncSession) -> None:
    """price_paise IS NULL is a distinct failure from "no creatives" - a
    house/admin campaign accidentally routed through checkout, say - so it
    gets its own code rather than the misleading "no_creatives"."""
    campaign = _campaign(price_paise=None, pricing_model=None, rate_card_version=None)
    db_session.add(campaign)
    await db_session.flush()
    await _creative(db_session, campaign, "pending")

    with pytest.raises(lifecycle.LifecycleError) as exc_info:
        await lifecycle.request_checkout(db_session, campaign)
    assert exc_info.value.code == "not_priced"


async def test_request_checkout_no_creatives_raises_no_creatives(db_session: AsyncSession) -> None:
    campaign = _campaign()
    db_session.add(campaign)
    await db_session.flush()

    with pytest.raises(lifecycle.LifecycleError) as exc_info:
        await lifecycle.request_checkout(db_session, campaign)
    assert exc_info.value.code == "no_creatives"


# ---------------------------------------------------------------------------
# maybe_activate conjunction matrix (the non-negotiable)


async def test_maybe_activate_paid_and_approved_activates(db_session: AsyncSession) -> None:
    campaign = _campaign(status="pending_moderation", paid_at=datetime.now(UTC))
    db_session.add(campaign)
    await db_session.flush()
    await _creative(db_session, campaign, "approved")

    assert await lifecycle.maybe_activate(db_session, campaign) is True
    assert campaign.status == "active"


async def test_maybe_activate_paid_with_pending_creative_stays_pending_moderation(
    db_session: AsyncSession,
) -> None:
    campaign = _campaign(status="pending_moderation", paid_at=datetime.now(UTC))
    db_session.add(campaign)
    await db_session.flush()
    await _creative(db_session, campaign, "approved")
    await _creative(db_session, campaign, "pending")

    assert await lifecycle.maybe_activate(db_session, campaign) is False
    assert campaign.status == "pending_moderation"


async def test_maybe_activate_approved_but_unpaid_never_activates(
    db_session: AsyncSession,
) -> None:
    """THREAT: activation-before-payment. A campaign that is somehow sitting
    in pending_moderation with an approved creative but no paid_at must NOT
    activate - payment is the OTHER half of the gate."""
    campaign = _campaign(status="pending_moderation", paid_at=None)
    db_session.add(campaign)
    await db_session.flush()
    await _creative(db_session, campaign, "approved")

    assert await lifecycle.maybe_activate(db_session, campaign) is False
    assert campaign.status == "pending_moderation"


async def test_maybe_activate_ignores_non_activatable_states(db_session: AsyncSession) -> None:
    """THREAT: approval must not reach into pending_payment (money hasn't
    even been requested yet) and flip it live."""
    campaign = _campaign(status="pending_payment", paid_at=None)
    db_session.add(campaign)
    await db_session.flush()
    await _creative(db_session, campaign, "approved")

    assert await lifecycle.maybe_activate(db_session, campaign) is False
    assert campaign.status == "pending_payment"


async def test_maybe_activate_no_creatives_never_activates(db_session: AsyncSession) -> None:
    campaign = _campaign(status="pending_moderation", paid_at=datetime.now(UTC))
    db_session.add(campaign)
    await db_session.flush()

    assert await lifecycle.maybe_activate(db_session, campaign) is False
    assert campaign.status == "pending_moderation"


async def test_maybe_activate_refreshes_a_stale_identity_mapped_campaign(
    db_session: AsyncSession,
) -> None:
    """Regression (Task 7 review round 2): SQLAlchemy's identity map does
    NOT repopulate an already-loaded object's attributes from a later
    SELECT - not even a locked one - unless the read explicitly refreshes
    it. This simulates, in one session, exactly what a concurrent
    transaction's committed write would look like from the other side of
    maybe_activate's row lock: the in-memory `campaign` object is left
    deliberately stale (paid_at=None) while a raw Core UPDATE sets paid_at
    on the underlying row directly, WITH `synchronize_session=False` so
    SQLAlchemy's default ORM-evaluate auto-sync (which would otherwise
    quietly patch `campaign.paid_at` itself and defeat the point of this
    test) is turned off - genuinely mimicking a write from a separate
    session/connection that this session doesn't know about. Without
    `session.refresh(campaign, with_for_update=True)` inside
    maybe_activate, this would evaluate the conjunction against the stale
    `None` and fail to activate even though the row is, in truth, paid."""
    campaign = _campaign(status="pending_moderation", paid_at=None)
    db_session.add(campaign)
    await db_session.flush()
    await _creative(db_session, campaign, "approved")

    await db_session.execute(
        update(Campaign)
        .where(Campaign.id == campaign.id)
        .values(paid_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    assert campaign.paid_at is None  # confirms the in-memory object is genuinely stale

    assert await lifecycle.maybe_activate(db_session, campaign) is True
    assert campaign.status == "active"
    assert campaign.paid_at is not None  # refresh picked up the Core UPDATE's value


# ---------------------------------------------------------------------------
# on_payment_event


async def test_on_payment_event_paid_activates_when_already_approved(
    db_session: AsyncSession,
) -> None:
    campaign = _campaign(status="pending_payment")
    db_session.add(campaign)
    await db_session.flush()
    await _creative(db_session, campaign, "approved")

    await lifecycle.on_payment_event(db_session, campaign.id, "paid")
    assert campaign.paid_at is not None
    assert campaign.status == "active"


async def test_on_payment_event_paid_with_pending_creative_stops_at_pending_moderation(
    db_session: AsyncSession,
) -> None:
    campaign = _campaign(status="pending_payment")
    db_session.add(campaign)
    await db_session.flush()
    await _creative(db_session, campaign, "pending")

    await lifecycle.on_payment_event(db_session, campaign.id, "paid")
    assert campaign.paid_at is not None
    assert campaign.status == "pending_moderation"


async def test_on_payment_event_paid_on_paused_campaign_leaves_it_paused(
    db_session: AsyncSession,
) -> None:
    """THREAT: a late/duplicate "paid" webhook must not resurrect an
    advertiser- or enforcement-paused campaign. maybe_activate's
    _ACTIVATABLE_FROM includes "paused" for the explicit resume ROUTE only -
    the payment webhook path must never reach into it."""
    campaign = _campaign(status="paused", paid_at=None)
    db_session.add(campaign)
    await db_session.flush()
    await _creative(db_session, campaign, "approved")

    await lifecycle.on_payment_event(db_session, campaign.id, "paid")
    assert campaign.paid_at is not None  # the payment fact is still recorded
    assert campaign.status == "paused"  # but it does not resurrect the campaign


async def test_on_payment_event_unknown_campaign_is_a_silent_noop(
    db_session: AsyncSession,
) -> None:
    await lifecycle.on_payment_event(db_session, uuid.uuid4(), "paid")  # must not raise


async def test_on_payment_event_unknown_event_string_is_ignored(db_session: AsyncSession) -> None:
    campaign = _campaign(status="active")
    db_session.add(campaign)
    await db_session.flush()

    await lifecycle.on_payment_event(db_session, campaign.id, "chargeback_dispute")
    assert campaign.status == "active"  # untouched


@pytest.mark.parametrize("status", ["active", "paused", "pending_payment", "pending_moderation"])
async def test_on_payment_event_refunded_pauses_and_zeroes_remaining_budget(
    db_session: AsyncSession, status: str
) -> None:
    campaign = _campaign(status=status, paid_at=datetime.now(UTC), budget_serves_total=5000)
    campaign.budget_serves_used = 1200
    db_session.add(campaign)
    await db_session.flush()

    await lifecycle.on_payment_event(db_session, campaign.id, "refunded")
    assert campaign.status == "paused"
    assert campaign.budget_serves_total == 1200  # == used: no serves remain


async def test_on_payment_event_refunded_leaves_draft_untouched(db_session: AsyncSession) -> None:
    campaign = _campaign(status="draft")
    db_session.add(campaign)
    await db_session.flush()

    await lifecycle.on_payment_event(db_session, campaign.id, "refunded")
    assert campaign.status == "draft"


async def test_resume_after_refund_stays_non_serving(db_session: AsyncSession) -> None:
    """The hole this closes: paid_at is never cleared by a refund, so a naive
    resume would pass maybe_activate's payment check. Zeroing the remaining
    budget keeps the resumed campaign durably non-serving even though its
    status flips back to active."""
    campaign = _campaign(status="active", paid_at=datetime.now(UTC), budget_serves_total=5000)
    campaign.budget_serves_used = 3000
    db_session.add(campaign)
    await db_session.flush()
    await _creative(db_session, campaign, "approved")

    await lifecycle.on_payment_event(db_session, campaign.id, "refunded")
    assert campaign.status == "paused"

    activated = await lifecycle.maybe_activate(db_session, campaign)
    assert activated is True  # paid_at + approved creative still pass the gate
    assert campaign.status == "active"
    # but the budget is exhausted, so display_status and consume_budget both
    # treat it as non-serving
    assert campaign.budget_serves_total is not None
    assert campaign.budget_serves_used >= campaign.budget_serves_total
    assert lifecycle.display_status(campaign, today=TODAY) == "exhausted"


# ---------------------------------------------------------------------------
# demote_to_moderation


async def test_demote_to_moderation_from_active(db_session: AsyncSession) -> None:
    campaign = _campaign(status="active")
    db_session.add(campaign)
    await db_session.flush()

    await lifecycle.demote_to_moderation(db_session, campaign)
    assert campaign.status == "pending_moderation"


async def test_demote_to_moderation_noop_when_not_active(db_session: AsyncSession) -> None:
    campaign = _campaign(status="paused")
    db_session.add(campaign)
    await db_session.flush()

    await lifecycle.demote_to_moderation(db_session, campaign)
    assert campaign.status == "paused"


# ---------------------------------------------------------------------------
# display_status


def test_display_status_active_within_flight_and_budget_is_active() -> None:
    campaign = Campaign(
        advertiser_business_id=uuid.uuid4(),
        name="x",
        status="active",
        flight_start=FLIGHT_START,
        flight_end=FLIGHT_END,
        budget_serves_total=5000,
        budget_serves_used=100,
    )
    assert lifecycle.display_status(campaign, today=TODAY) == "active"


def test_display_status_active_past_flight_is_expired() -> None:
    campaign = Campaign(
        advertiser_business_id=uuid.uuid4(),
        name="x",
        status="active",
        flight_start=FLIGHT_START,
        flight_end=TODAY - timedelta(days=1),
        budget_serves_total=None,
        budget_serves_used=0,
    )
    assert lifecycle.display_status(campaign, today=TODAY) == "expired"


def test_display_status_active_budget_exhausted_is_exhausted() -> None:
    campaign = Campaign(
        advertiser_business_id=uuid.uuid4(),
        name="x",
        status="active",
        flight_start=FLIGHT_START,
        flight_end=FLIGHT_END,
        budget_serves_total=5000,
        budget_serves_used=5000,
    )
    assert lifecycle.display_status(campaign, today=TODAY) == "exhausted"


def test_display_status_unlimited_budget_never_exhausted() -> None:
    campaign = Campaign(
        advertiser_business_id=uuid.uuid4(),
        name="x",
        status="active",
        flight_start=FLIGHT_START,
        flight_end=FLIGHT_END,
        budget_serves_total=None,
        budget_serves_used=999_999,
    )
    assert lifecycle.display_status(campaign, today=TODAY) == "active"


@pytest.mark.parametrize(
    "status", ["draft", "pending_payment", "pending_moderation", "paused", "archived"]
)
def test_display_status_non_active_is_passthrough(status: str) -> None:
    campaign = Campaign(
        advertiser_business_id=uuid.uuid4(),
        name="x",
        status=status,
        flight_start=FLIGHT_START,
        flight_end=FLIGHT_END,
    )
    assert lifecycle.display_status(campaign, today=TODAY) == status


# ---------------------------------------------------------------------------
# sweep_lifecycle


async def test_sweep_lifecycle_flips_expired_and_exhausted(db_session: AsyncSession) -> None:
    expired = _campaign(status="active", flight_end=TODAY - timedelta(days=1))
    exhausted = _campaign(
        status="active",
        flight_end=FLIGHT_END,
        budget_serves_total=1000,
    )
    exhausted.budget_serves_used = 1000
    untouched = _campaign(status="active", flight_end=FLIGHT_END, budget_serves_total=1000)
    untouched.budget_serves_used = 10
    already_paused = _campaign(status="paused", flight_end=TODAY - timedelta(days=1))
    db_session.add_all([expired, exhausted, untouched, already_paused])
    await db_session.flush()

    changed = await lifecycle.sweep_lifecycle(db_session, today=TODAY)
    assert changed == 2

    await db_session.refresh(expired)
    await db_session.refresh(exhausted)
    await db_session.refresh(untouched)
    await db_session.refresh(already_paused)
    assert expired.status == "expired"
    assert exhausted.status == "exhausted"
    assert untouched.status == "active"
    assert already_paused.status == "paused"  # sweep only ever reads FROM active


async def test_sweep_lifecycle_prefers_expired_over_exhausted(db_session: AsyncSession) -> None:
    """A campaign that is both past its flight AND budget-exhausted lands on
    "expired" - matching display_status's own precedence (flight checked
    first) rather than "exhausted"."""
    both = _campaign(
        status="active",
        flight_end=TODAY - timedelta(days=1),
        budget_serves_total=1000,
    )
    both.budget_serves_used = 1000
    db_session.add(both)
    await db_session.flush()

    changed = await lifecycle.sweep_lifecycle(db_session, today=TODAY)
    assert changed == 1
    await db_session.refresh(both)
    assert both.status == "expired"


async def test_sweep_lifecycle_recovers_stranded_paid_and_approved_campaign(
    db_session: AsyncSession,
) -> None:
    """Backstop for the maybe_activate race (Task 7 reviewer finding #1):
    directly simulates a campaign that is fully paid and approved but never
    got flipped to active (e.g. stranded by the pre-fix race, or a manual DB
    fixup) - the next worker tick must recover it rather than leaving it
    unservable forever with no advertiser-visible recovery path."""
    stranded = _campaign(status="pending_moderation", paid_at=datetime.now(UTC))
    not_yet_paid = _campaign(status="pending_moderation", paid_at=None)
    db_session.add_all([stranded, not_yet_paid])
    await db_session.flush()
    await _creative(db_session, stranded, "approved")
    await _creative(db_session, not_yet_paid, "approved")

    changed = await lifecycle.sweep_lifecycle(db_session, today=TODAY)
    assert changed == 1

    await db_session.refresh(stranded)
    await db_session.refresh(not_yet_paid)
    assert stranded.status == "active"
    assert not_yet_paid.status == "pending_moderation"  # still unpaid: not recovered
