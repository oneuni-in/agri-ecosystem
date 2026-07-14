# backend/core/alembic/versions/0014_notify_v1.py
"""D12 notify: templates/notifications/deliveries/preferences + seeds + flag.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-12

"""
# -- THREAT/NOTES:
# downgrade data loss: drops all notify tables (notifications, delivery
#   history, preferences) and the seeded templates + the notify.email_enabled
#   flag row. Acceptable pre-launch.
# locks: CREATE TABLE/TYPE + small bulk inserts; no existing-table rewrites.
# rollout: run after 0012 (app_rt default privileges in schema notify already
#   cover these tables). Deploy with or before the D12 notify code.

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

channel_enum = postgresql.ENUM("in_app", "sms", "email", name="notify_channel", schema="notify")
status_enum = postgresql.ENUM(
    "pending", "sent", "failed", "dead", name="delivery_status", schema="notify"
)
locale_enum = postgresql.ENUM("en", "ta", "hi", name="notify_locale", schema="notify")

templates_table = sa.table(
    "templates",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("key", sa.Text),
    # channel/locale are enum-typed in the DB; asyncpg's executemany rejects
    # a varchar bind against an enum column, so bind with the real enum
    # types here (not sa.Text) to avoid a DatatypeMismatchError on insert.
    sa.column("channel", channel_enum),
    sa.column("locale", locale_enum),
    sa.column("subject", sa.Text),
    sa.column("body", sa.Text),
    schema="notify",
)

# (key, channel, locale, subject, body) - every key ships en+ta+hi (CI gate)
SEED_TEMPLATES: list[tuple[str, str, str, str | None, str]] = [
    # welcome - in_app
    ("welcome", "in_app", "en", None, "Welcome to Agri, {agri_id}! Your account is ready."),
    ("welcome", "in_app", "ta", None, "அக்ரிக்கு வரவேற்கிறோம், {agri_id}! உங்கள் கணக்கு தயார்."),
    ("welcome", "in_app", "hi", None, "एग्री में आपका स्वागत है, {agri_id}! आपका खाता तैयार है।"),
    # welcome - email
    (
        "welcome",
        "email",
        "en",
        "Welcome to Agri",
        "Hello {agri_id}, your Agri account is ready. You can sign in on agri.in, milk.agri.in and organic.agri.in with one ID.",  # noqa: E501
    ),
    (
        "welcome",
        "email",
        "ta",
        "அக்ரிக்கு வரவேற்கிறோம்",
        "வணக்கம் {agri_id}, உங்கள் அக்ரி கணக்கு தயார். ஒரே ஐடியுடன் agri.in, milk.agri.in, organic.agri.in ஆகியவற்றில் உள்நுழையலாம்.",  # noqa: E501
    ),
    (
        "welcome",
        "email",
        "hi",
        "एग्री में आपका स्वागत है",
        "नमस्ते {agri_id}, आपका एग्री खाता तैयार है। एक ही आईडी से agri.in, milk.agri.in और organic.agri.in पर साइन इन करें।",  # noqa: E501
    ),
    # login_new_device - in_app
    (
        "login_new_device",
        "in_app",
        "en",
        None,
        "New login to your account from {device}. Not you? Review your devices.",
    ),
    (
        "login_new_device",
        "in_app",
        "ta",
        None,
        "{device} இலிருந்து உங்கள் கணக்கில் புதிய உள்நுழைவு. நீங்கள் இல்லையா? உங்கள் சாதனங்களைச் சரிபார்க்கவும்.",
    ),
    (
        "login_new_device",
        "in_app",
        "hi",
        None,
        "{device} से आपके खाते में नया लॉगिन हुआ। आप नहीं थे? अपने डिवाइस जांचें।",
    ),
    # login_new_device - sms
    (
        "login_new_device",
        "sms",
        "en",
        None,
        "Agri: new login from {device}. Not you? Review devices at id.agri.in/devices",
    ),
    (
        "login_new_device",
        "sms",
        "ta",
        None,
        "அக்ரி: {device} இலிருந்து புதிய உள்நுழைவு. நீங்கள் இல்லையா? id.agri.in/devices",
    ),
    (
        "login_new_device",
        "sms",
        "hi",
        None,
        "एग्री: {device} से नया लॉगिन। आप नहीं थे? id.agri.in/devices देखें",
    ),
    # login_new_device - email
    (
        "login_new_device",
        "email",
        "en",
        "New login to your Agri account",
        "A new login to your Agri account was made from {device}. If this wasn't you, review your devices at id.agri.in/devices.",  # noqa: E501
    ),
    (
        "login_new_device",
        "email",
        "ta",
        "உங்கள் அக்ரி கணக்கில் புதிய உள்நுழைவு",
        "{device} இலிருந்து உங்கள் அக்ரி கணக்கில் புதிய உள்நுழைவு நடந்தது. இது நீங்கள் இல்லையெனில், id.agri.in/devices இல் உங்கள் சாதனங்களைச் சரிபார்க்கவும்.",  # noqa: E501
    ),
    (
        "login_new_device",
        "email",
        "hi",
        "आपके एग्री खाते में नया लॉगिन",
        "{device} से आपके एग्री खाते में नया लॉगिन हुआ। यदि यह आप नहीं थे, तो id.agri.in/devices पर अपने डिवाइस जांचें।",  # noqa: E501
    ),
    # role_changed - in_app
    ("role_changed", "in_app", "en", None, "Your account role was updated: {role}."),
    ("role_changed", "in_app", "ta", None, "உங்கள் கணக்குப் பங்கு புதுப்பிக்கப்பட்டது: {role}."),
    ("role_changed", "in_app", "hi", None, "आपके खाते की भूमिका बदली गई: {role}।"),
    # generic_announce - in_app
    ("generic_announce", "in_app", "en", None, "{message}"),
    ("generic_announce", "in_app", "ta", None, "{message}"),
    ("generic_announce", "in_app", "hi", None, "{message}"),
    # generic_announce - email
    ("generic_announce", "email", "en", "Announcement from Agri", "{message}"),
    ("generic_announce", "email", "ta", "அக்ரி அறிவிப்பு", "{message}"),
    ("generic_announce", "email", "hi", "एग्री की घोषणा", "{message}"),
]


def upgrade() -> None:
    bind = op.get_bind()
    channel_enum.create(bind, checkfirst=True)
    status_enum.create(bind, checkfirst=True)
    locale_enum.create(bind, checkfirst=True)
    no_create = {"create_type": False}
    channel = postgresql.ENUM(
        "in_app", "sms", "email", name="notify_channel", schema="notify", **no_create
    )
    status = postgresql.ENUM(
        "pending", "sent", "failed", "dead", name="delivery_status", schema="notify", **no_create
    )
    locale = postgresql.ENUM("en", "ta", "hi", name="notify_locale", schema="notify", **no_create)

    op.create_table(
        "templates",
        pk_column(),
        *timestamp_columns(),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("channel", channel, nullable=False),
        sa.Column("locale", locale, nullable=False),
        sa.Column("subject", sa.Text, nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.UniqueConstraint("key", "channel", "locale"),
        schema="notify",
    )
    op.create_table(
        "notifications",
        pk_column(),
        *timestamp_columns(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_key", sa.Text, nullable=False),
        sa.Column(
            "payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("locale", locale, nullable=False, server_default="en"),
        sa.Column("read_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="notify",
    )
    op.create_index(None, "notifications", ["user_id"], schema="notify")
    # unread-count is the hot query: partial index on the unread rows only
    op.create_index(
        "ix_notify_notifications_unread",
        "notifications",
        ["user_id"],
        schema="notify",
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_table(
        "deliveries",
        pk_column(),
        *timestamp_columns(),
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notify.notifications.id"),
            nullable=False,
        ),
        sa.Column("channel", channel, nullable=False),
        sa.Column("status", status, nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("destination", sa.Text, nullable=True),
        sa.Column("provider_ref", sa.Text, nullable=True),
        sa.Column("cost", sa.Numeric(10, 4), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        schema="notify",
    )
    op.create_index(None, "deliveries", ["notification_id"], schema="notify")
    op.create_index(
        "ix_notify_deliveries_retry_due",
        "deliveries",
        ["next_attempt_at"],
        schema="notify",
        postgresql_where=sa.text("status = 'failed'"),
    )
    op.create_table(
        "preferences",
        pk_column(),
        *timestamp_columns(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", channel, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("user_id", "channel"),
        schema="notify",
    )

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
    op.execute(
        sa.text(
            "INSERT INTO public.feature_flags (key, enabled, description) "
            "VALUES ('notify.email_enabled', false, "
            "'D12: real/email sends for the notify engine (ZeptoMail driver)') "
            "ON CONFLICT (key) DO NOTHING"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM public.feature_flags WHERE key = 'notify.email_enabled'"))
    op.drop_table("preferences", schema="notify")
    op.drop_table("deliveries", schema="notify")
    op.drop_table("notifications", schema="notify")
    op.drop_table("templates", schema="notify")
    for enum in (status_enum, channel_enum, locale_enum):
        enum.drop(op.get_bind(), checkfirst=True)
