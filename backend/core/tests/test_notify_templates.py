"""D12 non-negotiable 4: every (key, channel) exists in ALL 3 locales, or CI
fails. Also pins the seeded catalogue so a dropped seed is loud."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.models import Template
from shared.i18n import SUPPORTED_LOCALES

EXPECTED_CHANNELS = {
    "welcome": {"in_app", "email"},
    "login_new_device": {"in_app", "sms", "email"},
    "role_changed": {"in_app"},
    "generic_announce": {"in_app", "email"},
    # D16 claim/verification decisions (in-app only: directory events carry
    # no email/locale - the module may not read identity's tables)
    "claim_approved": {"in_app"},
    "claim_rejected": {"in_app"},
    "verification_approved": {"in_app"},
    "verification_rejected": {"in_app"},
    # D18 review moderation (in-app only, same rationale as claim/verification)
    "review_approved": {"in_app"},
    # D18 leads (in-app only, same rationale as claim/verification)
    "lead_received": {"in_app", "push"},
    "lead_response": {"in_app", "push"},
    # D20 billing
    "dunning_payment_failed": {"in_app", "email"},
    "dunning_reminder": {"in_app", "email"},
    "subscription_canceled": {"in_app", "email"},
    "subscription_activated": {"in_app", "email"},
}


async def test_every_key_channel_pair_has_all_three_locales(db_session: AsyncSession) -> None:
    rows = (await db_session.scalars(select(Template))).all()
    seen: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        seen.setdefault((row.key, row.channel), set()).add(row.locale)
    assert seen, "template seed missing entirely"
    incomplete = {
        pair: locales for pair, locales in seen.items() if locales != set(SUPPORTED_LOCALES)
    }
    assert not incomplete, f"templates missing locales: {incomplete}"


async def test_seeded_catalogue_matches_spec(db_session: AsyncSession) -> None:
    rows = (await db_session.scalars(select(Template))).all()
    by_key: dict[str, set[str]] = {}
    for row in rows:
        by_key.setdefault(row.key, set()).add(row.channel)
    assert by_key == EXPECTED_CHANNELS


async def test_email_templates_have_subjects(db_session: AsyncSession) -> None:
    rows = (await db_session.scalars(select(Template).where(Template.channel == "email"))).all()
    assert rows and all(row.subject for row in rows)
