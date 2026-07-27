# backend/core/alembic/versions/0027_push_channel.py
"""Web push channel: enum value, subscriptions table, templates, flag (D28).

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-27

"""
# -- THREAT/NOTES:
# - ALTER TYPE ... ADD VALUE cannot run inside the migration transaction on
#   PG16, so it executes in an autocommit block; IF NOT EXISTS keeps
#   migrate_check's downgrade->re-upgrade green.
# - downgrade CANNOT remove an enum value (PG limitation) - 'push' remains
#   as harmless residue; the table, templates and flag ARE removed. Any
#   deliveries rows with channel='push' would block even that, but downgrade
#   from a push-active system implies accepting notify-history loss anyway.
# - push_subscriptions.endpoint is a durable device identifier (same
#   never-log class as deliveries.destination). Explicit per-table GRANT for
#   app_rt only (0023 precedent) - NEVER a blanket GRANT ON ALL TABLES.
# - flag notify.push_enabled seeds FALSE: no push leaves the building until
#   the owner provisions VAPID keys and flips it (email_enabled precedent).

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)

channel_enum = postgresql.ENUM(name="notify_channel", schema="notify", create_type=False)
locale_enum = postgresql.ENUM(name="notify_locale", schema="notify", create_type=False)

templates_table = sa.table(
    "templates",
    sa.column("id", _uuid),
    sa.column("key", sa.Text),
    # enum-typed binds required by asyncpg executemany (0014 trap)
    sa.column("channel", channel_enum),
    sa.column("locale", locale_enum),
    sa.column("subject", sa.Text),
    sa.column("body", sa.Text),
    schema="notify",
)

# (key, locale, subject-as-push-title, body) - every key ships en+ta+hi
# (tests/test_notify_templates.py gate). The Template model has no separate
# title column; push renders subject as the notification title.
SEED_PUSH_TEMPLATES: list[tuple[str, str, str, str]] = [
    (
        "lead_received",
        "en",
        "New enquiry — {business_name}",
        "You have a new {inquiry_type} enquiry. Open Milk.in to reply.",
    ),
    (
        "lead_received",
        "ta",
        "புதிய விசாரணை — {business_name}",
        "உங்களுக்கு புதிய {inquiry_type} விசாரணை வந்துள்ளது. பதிலளிக்க Milk.in-ஐ திறக்கவும்.",
    ),
    (
        "lead_received",
        "hi",
        "नई पूछताछ — {business_name}",
        "आपके लिए नई {inquiry_type} पूछताछ आई है। जवाब देने के लिए Milk.in खोलें।",
    ),
    (
        "lead_response",
        "en",
        "{business_name} replied",
        "{business_name} replied to your request. Open Milk.in to see it.",
    ),
    (
        "lead_response",
        "ta",
        "{business_name} பதிலளித்துள்ளது",
        "உங்கள் கோரிக்கைக்கு {business_name} பதிலளித்துள்ளது. பார்க்க Milk.in-ஐ திறக்கவும்.",
    ),
    (
        "lead_response",
        "hi",
        "{business_name} ने जवाब दिया",
        "आपके अनुरोध का {business_name} ने जवाब दिया है। देखने के लिए Milk.in खोलें।",
    ),
]


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE notify.notify_channel ADD VALUE IF NOT EXISTS 'push'")

    op.create_table(
        "push_subscriptions",
        pk_column(),
        sa.Column("user_id", _uuid, nullable=False),
        sa.Column("endpoint", sa.Text, nullable=False),
        sa.Column("p256dh", sa.Text, nullable=False),
        sa.Column("auth", sa.Text, nullable=False),
        sa.Column("ua_label", sa.Text, nullable=True),
        *timestamp_columns(),
        sa.UniqueConstraint("endpoint"),
        schema="notify",
    )
    op.create_index(
        "ix_notify_push_subscriptions_user_id",
        "push_subscriptions",
        ["user_id"],
        schema="notify",
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON notify.push_subscriptions TO app_rt")

    op.bulk_insert(
        templates_table,
        [
            {
                "id": uuid6.uuid7(),
                "key": key,
                "channel": "push",
                "locale": loc,
                "subject": subject,
                "body": body,
            }
            for key, loc, subject, body in SEED_PUSH_TEMPLATES
        ],
    )
    op.execute(
        sa.text(
            "INSERT INTO public.feature_flags (key, enabled, description) "
            "VALUES ('notify.push_enabled', false, "
            "'D28: web-push sends for the notify engine (VAPID driver)') "
            "ON CONFLICT (key) DO NOTHING"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM public.feature_flags WHERE key = 'notify.push_enabled'"))
    op.execute(sa.text("DELETE FROM notify.templates WHERE channel = 'push'"))
    op.drop_index("ix_notify_push_subscriptions_user_id", "push_subscriptions", schema="notify")
    op.drop_table("push_subscriptions", schema="notify")
    # enum value 'push' remains - see THREAT/NOTES.
