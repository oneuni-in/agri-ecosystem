# backend/core/alembic/versions/0021_billing_v1.py
"""D20 billing: subscriptions + invoices + payment_events, per-table app_rt
grants, and the dunning/lifecycle notify templates.

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-21

"""
# -- THREAT/NOTES:
# - payment_events is the raw (scrubbed) webhook log and the idempotency
#   ledger - append-only BY GRANT for app_rt, exactly like audit.entries
#   (0013) and leads.contact_reveals (0020). Rows are inserted with their
#   final `outcome` in the same transaction that processed the webhook, so
#   the runtime role never needs UPDATE.
# - schema "billing" exists since 0001. Card/instrument data never lands
#   here: the webhook handler scrubs payloads before insert
#   (modules/billing/sanitize.py); this migration only shapes storage.
# - locks: CREATE TABLE + small bulk inserts; no existing-table rewrites.

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

channel_enum = postgresql.ENUM(
    "in_app", "sms", "email", name="notify_channel", schema="notify", create_type=False
)
locale_enum = postgresql.ENUM(
    "en", "ta", "hi", name="notify_locale", schema="notify", create_type=False
)

templates_table = sa.table(
    "templates",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("key", sa.Text),
    sa.column("channel", channel_enum),
    sa.column("locale", locale_enum),
    sa.column("subject", sa.Text),
    sa.column("body", sa.Text),
    schema="notify",
)

# (key, channel, locale, subject, body) - every key ships en+ta+hi (CI gate).
# Vars come from the billing event payload: {business_name}, {tier}.
SEED_TEMPLATES: list[tuple[str, str, str, str | None, str]] = [
    (
        "dunning_payment_failed",
        "in_app",
        "en",
        None,
        "Payment failed for {business_name}. We'll retry automatically - please check your payment method.",  # noqa: E501
    ),
    (
        "dunning_payment_failed",
        "in_app",
        "ta",
        None,
        "{business_name} கட்டணம் தோல்வியடைந்தது. மீண்டும் முயற்சிப்போம் - உங்கள் கட்டண முறையைச் சரிபார்க்கவும்.",
    ),
    (
        "dunning_payment_failed",
        "in_app",
        "hi",
        None,
        "{business_name} का भुगतान विफल रहा। हम फिर से प्रयास करेंगे - कृपया अपनी भुगतान विधि जाँचें।",
    ),
    (
        "dunning_payment_failed",
        "email",
        "en",
        "Payment failed - action needed",
        "Payment for {business_name}'s {tier} subscription failed. We'll retry automatically - please check your payment method to avoid interruption.",  # noqa: E501
    ),
    (
        "dunning_payment_failed",
        "email",
        "ta",
        "கட்டணம் தோல்வியடைந்தது - நடவடிக்கை தேவை",
        "{business_name} நிறுவனத்தின் {tier} சந்தா கட்டணம் தோல்வியடைந்தது. மீண்டும் முயற்சிப்போம் - இடையூறு தவிர்க்க உங்கள் கட்டண முறையைச் சரிபார்க்கவும்.",  # noqa: E501
    ),
    (
        "dunning_payment_failed",
        "email",
        "hi",
        "भुगतान विफल - कार्रवाई आवश्यक",
        "{business_name} की {tier} सदस्यता का भुगतान विफल रहा। हम फिर से प्रयास करेंगे - रुकावट से बचने के लिए कृपया अपनी भुगतान विधि जाँचें।",  # noqa: E501
    ),
    (
        "dunning_reminder",
        "in_app",
        "en",
        None,
        "Reminder: payment for {business_name} is still pending. Update your payment method to keep your {tier} subscription.",  # noqa: E501
    ),
    (
        "dunning_reminder",
        "in_app",
        "ta",
        None,
        "நினைவூட்டல்: {business_name} கட்டணம் இன்னும் நிலுவையில் உள்ளது. {tier} சந்தாவைத் தொடர கட்டண முறையைப் புதுப்பிக்கவும்.",  # noqa: E501
    ),
    (
        "dunning_reminder",
        "in_app",
        "hi",
        None,
        "अनुस्मारक: {business_name} का भुगतान अभी भी लंबित है। {tier} सदस्यता जारी रखने के लिए भुगतान विधि अपडेट करें।",  # noqa: E501
    ),
    (
        "dunning_reminder",
        "email",
        "en",
        "Reminder: subscription payment pending",
        "Payment for {business_name}'s {tier} subscription is still pending. Update your payment method to keep your subscription active.",  # noqa: E501
    ),
    (
        "dunning_reminder",
        "email",
        "ta",
        "நினைவூட்டல்: சந்தா கட்டணம் நிலுவையில்",
        "{business_name} நிறுவனத்தின் {tier} சந்தா கட்டணம் இன்னும் நிலுவையில் உள்ளது. சந்தாவைத் தொடர உங்கள் கட்டண முறையைப் புதுப்பிக்கவும்.",  # noqa: E501
    ),
    (
        "dunning_reminder",
        "email",
        "hi",
        "अनुस्मारक: सदस्यता भुगतान लंबित",
        "{business_name} की {tier} सदस्यता का भुगतान अभी भी लंबित है। सदस्यता सक्रिय रखने के लिए अपनी भुगतान विधि अपडेट करें।",  # noqa: E501
    ),
    (
        "subscription_canceled",
        "in_app",
        "en",
        None,
        "Your {tier} subscription for {business_name} has been canceled.",
    ),
    (
        "subscription_canceled",
        "in_app",
        "ta",
        None,
        "{business_name}க்கான உங்கள் {tier} சந்தா ரத்து செய்யப்பட்டது.",
    ),
    (
        "subscription_canceled",
        "in_app",
        "hi",
        None,
        "{business_name} के लिए आपकी {tier} सदस्यता रद्द कर दी गई है।",
    ),
    (
        "subscription_canceled",
        "email",
        "en",
        "Subscription canceled",
        "Your {tier} subscription for {business_name} has been canceled. You can subscribe again any time from the business console.",  # noqa: E501
    ),
    (
        "subscription_canceled",
        "email",
        "ta",
        "சந்தா ரத்து செய்யப்பட்டது",
        "{business_name}க்கான உங்கள் {tier} சந்தா ரத்து செய்யப்பட்டது. வணிக கன்சோலில் இருந்து எப்போது வேண்டுமானாலும் மீண்டும் சந்தா செய்யலாம்.",  # noqa: E501
    ),
    (
        "subscription_canceled",
        "email",
        "hi",
        "सदस्यता रद्द",
        "{business_name} के लिए आपकी {tier} सदस्यता रद्द कर दी गई है। आप बिज़नेस कंसोल से कभी भी फिर से सदस्यता ले सकते हैं।",  # noqa: E501
    ),
    (
        "subscription_activated",
        "in_app",
        "en",
        None,
        "Your {tier} subscription for {business_name} is active. Thanks for supporting Agri!",
    ),
    (
        "subscription_activated",
        "in_app",
        "ta",
        None,
        "{business_name}க்கான உங்கள் {tier} சந்தா செயலில் உள்ளது. நன்றி!",
    ),
    (
        "subscription_activated",
        "in_app",
        "hi",
        None,
        "{business_name} के लिए आपकी {tier} सदस्यता सक्रिय है। धन्यवाद!",
    ),
    (
        "subscription_activated",
        "email",
        "en",
        "Subscription active",
        "Your {tier} subscription for {business_name} is now active. Thanks for supporting Agri!",
    ),
    (
        "subscription_activated",
        "email",
        "ta",
        "சந்தா செயலில் உள்ளது",
        "{business_name}க்கான உங்கள் {tier} சந்தா இப்போது செயலில் உள்ளது. நன்றி!",
    ),
    (
        "subscription_activated",
        "email",
        "hi",
        "सदस्यता सक्रिय",
        "{business_name} के लिए आपकी {tier} सदस्यता अब सक्रिय है। धन्यवाद!",
    ),
]


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tier", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("current_period_end", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("razorpay_sub_id", sa.Text, nullable=True, unique=True),
        sa.Column("dunning_attempt", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("next_retry_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("past_due_since", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("tier IN ('growth', 'pro')", name="subscriptions_tier_check"),
        sa.CheckConstraint(
            "status IN ('active', 'past_due', 'canceled')", name="subscriptions_status_check"
        ),
        schema="billing",
    )
    op.create_index(
        "ix_billing_subscriptions_business_id",
        "subscriptions",
        ["business_id"],
        schema="billing",
    )
    op.create_index(
        "ix_billing_subscriptions_live_business",
        "subscriptions",
        ["business_id"],
        unique=True,
        schema="billing",
        postgresql_where=sa.text("status != 'canceled'"),
    )
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("billing.subscriptions.id"),
            nullable=False,
        ),
        sa.Column("amount_paise", sa.Integer, nullable=False),
        sa.Column("currency", sa.Text, nullable=False, server_default="INR"),
        sa.Column("status", sa.Text, nullable=False, server_default="issued"),
        sa.Column("razorpay_invoice_id", sa.Text, nullable=True, unique=True),
        sa.Column("pdf_key", sa.Text, nullable=True),
        sa.Column("period_start", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("period_end", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('issued', 'paid', 'failed', 'void')", name="invoices_status_check"
        ),
        schema="billing",
    )
    op.create_index(
        "ix_billing_invoices_subscription_id", "invoices", ["subscription_id"], schema="billing"
    )
    op.create_table(
        "payment_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.Text, nullable=False, server_default="razorpay"),
        sa.Column("provider_event_id", sa.Text, nullable=False, unique=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="billing",
    )
    # explicit per-table grants (0019/0020 precedent - never schema-wide)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON billing.subscriptions TO app_rt")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON billing.invoices TO app_rt")
    op.execute("GRANT SELECT, INSERT ON billing.payment_events TO app_rt")
    # payment_events is append-only BY GRANT - see THREAT block above.
    op.execute("REVOKE UPDATE, DELETE ON billing.payment_events FROM app_rt")

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
        "DELETE FROM notify.templates WHERE key IN "
        "('dunning_payment_failed','dunning_reminder',"
        "'subscription_canceled','subscription_activated')"
    )
    op.drop_table("payment_events", schema="billing")
    op.drop_table("invoices", schema="billing")  # drops ix_billing_invoices_subscription_id too
    op.drop_table("subscriptions", schema="billing")  # drops both subscription indexes too
