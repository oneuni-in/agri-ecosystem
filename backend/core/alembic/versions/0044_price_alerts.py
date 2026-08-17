"""A-U2 AG-A16: mandi price-alert subscriptions + their notify templates.

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-17

The A-U1 home carries a "mandi alerts for {pincode}" card whose CTA was a
door to /notifications, because nothing existed behind it. This is what
goes behind it.

SHAPE: one row per (user, pincode), NOT per commodity. The card asks for
alerts for an AREA, and that is also the honest unit — a farmer wants to
know what their own mandi did this morning, and picking commodities off a
list is a form the card does not have. The daily digest covers whatever
curated commodities reported in that district.

`last_notified_on` is the once-a-day latch. The pull is safe to re-run
(and is re-run, deliberately, because the source only serves the live
day), so without it a retry would notify twice for the same prices.

No FK to identity: modules never read each other's tables, so `user_id`
is stored bare and resolved by notify at delivery time.
"""

# -- THREAT/NOTES:
# - New table + 6 template rows (2 keys x 3 locales is the tests/
#   test_notify_templates.py gate; this ships 1 key x 3 locales for
#   in_app). No existing table altered.
# - THIS TABLE HOLDS USER DATA — the first in market_data to do so. It is
#   a subscription: user_id + pincode, no contact details (notify resolves
#   those at send time), no free text, nothing a user typed. DPDP-wise it
#   is consent-first by construction: a row exists only because someone
#   asked for alerts, and DELETE removes it.
# - Soft delete, so an unsubscribe is auditable rather than a silent gap,
#   and the read path filters deleted rows.
# - UNIQUE (user_id, pincode) makes subscribe idempotent: pressing the
#   button twice cannot produce two notifications a day.
# - Per-user volume is capped in the service (settings.price_alert_max_
#   per_user), and notify's own hourly cap is the second brake.
# - downgrade drops the table and removes the seeded templates.

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, soft_delete_column, timestamp_columns

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEMPLATE_KEY = "mandi_price_alert"

# (locale, body). in_app only: a price digest is not worth an SMS, and the
# event carries no destination, which is what keeps market_data
# independent of identity (the review.approved precedent).
# Vars: {market} {as_of} {top} {count}
_TEMPLATES: list[tuple[str, str]] = [
    ("en", "{market} · {as_of}: {top}. {count} commodities updated today."),
    ("ta", "{market} · {as_of}: {top}. இன்று {count} பொருட்களின் விலை புதுப்பிக்கப்பட்டது."),
    ("hi", "{market} · {as_of}: {top}. आज {count} जिंसों के भाव अपडेट हुए।"),
]


def upgrade() -> None:
    op.create_table(
        "price_alerts",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        # No FK: modules never read identity's tables. notify resolves the
        # recipient from this id at delivery time.
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("pincode", sa.Text, nullable=False),
        # Once-a-day latch. The daily pull is re-run on purpose (the source
        # serves only the live day), so this is what stops a retry from
        # notifying twice for the same prices.
        sa.Column("last_notified_on", sa.Date, nullable=True),
        schema="market",
    )
    op.create_unique_constraint(
        "uq_price_alerts_user_pincode", "price_alerts", ["user_id", "pincode"], schema="market"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON market.price_alerts TO app_rt")

    templates = sa.table(
        "templates",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("key", sa.Text),
        sa.column(
            "channel", postgresql.ENUM(name="notify_channel", schema="notify", create_type=False)
        ),
        sa.column(
            "locale", postgresql.ENUM(name="notify_locale", schema="notify", create_type=False)
        ),
        sa.column("subject", sa.Text),
        sa.column("body", sa.Text),
        schema="notify",
    )
    op.bulk_insert(
        templates,
        [
            {
                "id": uuid6.uuid7(),
                "key": TEMPLATE_KEY,
                "channel": "in_app",
                "locale": locale,
                "subject": None,
                "body": body,
            }
            for locale, body in _TEMPLATES
        ],
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM notify.templates WHERE key = '{TEMPLATE_KEY}'")
    op.drop_table("price_alerts", schema="market")
