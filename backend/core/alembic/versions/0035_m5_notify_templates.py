# backend/core/alembic/versions/0035_m5_notify_templates.py
"""M5 Task 12: notify templates for the ad-invoice email (with PDF
attachment), campaign activation, and creative rejection events - the
0021/0027 SEED_TEMPLATES pattern, en/ta/hi.

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-05

"""
# -- THREAT/NOTES:
# - Pure data seed into the existing notify.templates table (0014) - no
#   schema change, no lock beyond the small bulk insert.
# - `ad_invoice`/`campaign_activated` ship email+in_app; `creative_rejected`
#   ships in_app only (same "directory/ads events carry no destination for
#   THIS one" rationale as claim_rejected/review_approved in 0017/0019 -
#   except here it's simply an editorial call: a rejected creative is a
#   normal in-console workflow nudge, not worth an email). notify's own
#   EVENT_ROUTES (modules/notify/consumers.py) is what actually wires these
#   keys to the `billing.ad_invoice`/`campaign.activated`/`creative.rejected`
#   bus events - this migration only ships the copy.
# - downgrade deletes the three new keys across all channels/locales; no
#   other migration depends on them existing.

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

channel_enum = postgresql.ENUM(name="notify_channel", schema="notify", create_type=False)
locale_enum = postgresql.ENUM(name="notify_locale", schema="notify", create_type=False)

templates_table = sa.table(
    "templates",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("key", sa.Text),
    # enum-typed binds required by asyncpg executemany (0014 trap)
    sa.column("channel", channel_enum),
    sa.column("locale", locale_enum),
    sa.column("subject", sa.Text),
    sa.column("body", sa.Text),
    schema="notify",
)

NEW_KEYS = ("ad_invoice", "campaign_activated", "creative_rejected")

# (key, channel, locale, subject, body) - every key ships en+ta+hi
# (tests/test_notify_templates.py gate). Vars come from the event payload:
# ad_invoice: {invoice_number}, {total}, {business_name} (billing's
# _pending_notification-shaped payload, modules/billing/ad_orders.py's
# run_invoice_pdf_sweep); campaign_activated: {campaign_name},
# {business_name} (modules/ads/moderation_sources.py's _activation_event);
# creative_rejected: {campaign_name} (same module's _rejection_event).
SEED_TEMPLATES: list[tuple[str, str, str, str | None, str]] = [
    (
        "ad_invoice",
        "in_app",
        "en",
        None,
        "Your invoice {invoice_number} for {business_name} is ready - Rs. {total}.",
    ),
    (
        "ad_invoice",
        "in_app",
        "ta",
        None,
        "{business_name}க்கான உங்கள் விலைப்பட்டியல் {invoice_number} தயார் - Rs. {total}.",
    ),
    (
        "ad_invoice",
        "in_app",
        "hi",
        None,
        "{business_name} के लिए आपका इनवॉइस {invoice_number} तैयार है - Rs. {total}।",
    ),
    (
        "ad_invoice",
        "email",
        "en",
        "Your Milk.in ads invoice {invoice_number}",
        "Your invoice {invoice_number} for {business_name}'s ad campaign is ready. Amount: Rs. {total}. The PDF is attached to this email.",  # noqa: E501
    ),
    (
        "ad_invoice",
        "email",
        "ta",
        "உங்கள் Milk.in விலைப்பட்டியல் {invoice_number}",
        "{business_name} நிறுவனத்தின் விளம்பரப் பிரச்சாரத்திற்கான விலைப்பட்டியல் {invoice_number} தயார். தொகை: Rs. {total}. PDF இந்த மின்னஞ்சலில் இணைக்கப்பட்டுள்ளது.",  # noqa: E501
    ),
    (
        "ad_invoice",
        "email",
        "hi",
        "आपका Milk.in विज्ञापन इनवॉइस {invoice_number}",
        "{business_name} के विज्ञापन अभियान का इनवॉइस {invoice_number} तैयार है। राशि: Rs. {total}। PDF इस ईमेल में संलग्न है।",  # noqa: E501
    ),
    (
        "campaign_activated",
        "in_app",
        "en",
        None,
        "Your campaign {campaign_name} is live.",
    ),
    (
        "campaign_activated",
        "in_app",
        "ta",
        None,
        "{campaign_name} பிரச்சாரம் இப்போது செயலில் உள்ளது.",
    ),
    (
        "campaign_activated",
        "in_app",
        "hi",
        None,
        "{campaign_name} अभियान अब सक्रिय है।",
    ),
    (
        "campaign_activated",
        "email",
        "en",
        "Your campaign {campaign_name} is live",
        "Great news - your campaign {campaign_name} for {business_name} is now live and serving ads.",  # noqa: E501
    ),
    (
        "campaign_activated",
        "email",
        "ta",
        "{campaign_name} பிரச்சாரம் செயலில் உள்ளது",
        "{business_name} நிறுவனத்திற்கான {campaign_name} பிரச்சாரம் இப்போது செயலில் உள்ளது, விளம்பரங்கள் காட்டப்படுகின்றன.",  # noqa: E501
    ),
    (
        "campaign_activated",
        "email",
        "hi",
        "आपका अभियान {campaign_name} लाइव है",
        "बधाई हो - {business_name} के लिए {campaign_name} अभियान अब सक्रिय है और विज्ञापन दिखा रहा है।",  # noqa: E501
    ),
    (
        "creative_rejected",
        "in_app",
        "en",
        None,
        "A creative on {campaign_name} needs changes.",
    ),
    (
        "creative_rejected",
        "in_app",
        "ta",
        None,
        "{campaign_name} பிரச்சாரத்தில் ஒரு விளம்பரப் படைப்புக்கு மாற்றங்கள் தேவை.",
    ),
    (
        "creative_rejected",
        "in_app",
        "hi",
        None,
        "{campaign_name} अभियान में एक क्रिएटिव को बदलाव की आवश्यकता है।",
    ),
]


def upgrade() -> None:
    op.bulk_insert(
        templates_table,
        [
            {
                "id": uuid6.uuid7(),
                "key": key,
                "channel": chan,
                "locale": loc,
                "subject": subject,
                "body": body,
            }
            for key, chan, loc, subject, body in SEED_TEMPLATES
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM notify.templates WHERE key = ANY(:keys)").bindparams(keys=NEW_KEYS)
    )
