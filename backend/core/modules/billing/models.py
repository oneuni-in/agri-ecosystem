"""Billing ORM models (D20/M5). Money-in only: subscriptions + ad orders +
invoices + the raw (scrubbed) webhook log, plus the append-only ad-revenue
ledger (M5 Task 9). No card/instrument data ever lands here - Razorpay
hosted flows hold the instrument; we store provider ids and amounts only.
payment_events (0021) and ledger_entries (0034) are append-only by grant."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, TimestampMixin, UUIDv7PKMixin


class Subscription(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("tier IN ('growth', 'pro')", name="subscriptions_tier_check"),
        CheckConstraint(
            "status IN ('active', 'past_due', 'canceled')", name="subscriptions_status_check"
        ),
        Index(
            "ix_billing_subscriptions_live_business",
            "business_id",
            unique=True,
            postgresql_where=text("status != 'canceled'"),
        ),
        {"schema": "billing"},
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False, index=True
    )
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    current_period_end: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=True
    )
    razorpay_sub_id: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    dunning_attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_retry_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=True
    )
    past_due_since: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=True
    )


class AdOrder(UUIDv7PKMixin, TimestampMixin, Base):
    """M5 Task 9: one Razorpay Payment Link per checkout attempt for a
    self-serve ad campaign. `quote` freezes the price decomposition ads
    handed billing at checkout time (audit snapshot - never re-derived on
    read). The partial unique index enforces "at most one LIVE order per
    campaign": a campaign with a `created` or `paid` order cannot start a
    second checkout, but a `failed`/`expired`/`refunded` order frees the
    campaign for a fresh attempt."""

    __tablename__ = "ad_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'paid', 'failed', 'expired', 'refunded')",
            name="ck_billing_ad_orders_status",
        ),
        CheckConstraint("subtotal_paise >= 0", name="ck_billing_ad_orders_subtotal_nonneg"),
        CheckConstraint("gst_paise >= 0", name="ck_billing_ad_orders_gst_nonneg"),
        CheckConstraint("total_paise >= 0", name="ck_billing_ad_orders_total_nonneg"),
        Index(
            "uq_billing_ad_orders_live",
            "campaign_id",
            unique=True,
            postgresql_where=text("status IN ('created', 'paid')"),
        ),
        Index("ix_billing_ad_orders_campaign_id", "campaign_id"),
        Index("ix_billing_ad_orders_razorpay_payment_id", "razorpay_payment_id"),
        {"schema": "billing"},
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="created")
    subtotal_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    gst_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    total_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default="INR")
    quote: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    buyer_gstin: Mapped[str | None] = mapped_column(Text, nullable=True)
    razorpay_plink_id: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class BillingLedgerEntry(UUIDv7PKMixin, Base):
    """M5 Task 9: append-only ad-revenue ledger (coins.ledger_entries /
    audit.entries precedent - DB trigger + revoked grants, never updated or
    deleted). Never named `LedgerEntry`: tests/lint_checks.py's ledger-write
    scanner regex-matches `LedgerEntry\\s*\\(` repo-wide for the COINS module
    only, and this class must not spuriously trip (or hide behind) that gate."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('ad_charge', 'ad_refund')", name="ck_billing_ledger_entries_type"
        ),
        CheckConstraint(
            "(entry_type = 'ad_charge' AND amount_paise > 0)"
            " OR (entry_type = 'ad_refund' AND amount_paise < 0)",
            name="ck_billing_ledger_entries_sign",
        ),
        Index("ix_billing_ledger_entries_campaign_id", "campaign_id"),
        Index("ix_billing_ledger_entries_razorpay_payment_id", "razorpay_payment_id"),
        {"schema": "billing"},
    )

    entry_type: Mapped[str] = mapped_column(Text, nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default="INR")
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("billing.ad_orders.id"), nullable=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=True
    )
    business_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    razorpay_payment_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )


class Invoice(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "status IN ('issued', 'paid', 'failed', 'void')", name="invoices_status_check"
        ),
        # M5 (0034): an invoice now has TWO possible parents - a subscription
        # (D20 recurring billing) or an ad order (M5 self-serve campaigns).
        # Exactly one row-producing side ever sets its FK; both NULL or both
        # set would mean "belongs to nothing"/"belongs to two things", so the
        # CHECK only rules out the both-NULL case (belongs to nothing).
        CheckConstraint(
            "subscription_id IS NOT NULL OR order_id IS NOT NULL",
            name="ck_billing_invoices_parent",
        ),
        {"schema": "billing"},
    )

    # M5 (0034): nullable now - an ad-order invoice has order_id set and
    # subscription_id NULL instead.
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        ForeignKey("billing.subscriptions.id"),
        nullable=True,
        index=True,
    )
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default="INR")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="issued")
    razorpay_invoice_id: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    pdf_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=True
    )
    period_end: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=True
    )
    # M5 (0034) ad-order invoice fields. order_id is the ad-order parent;
    # invoice_number is the ops-facing sequential number (billing.invoice_
    # number_seq, Task 10 fills it in on generation); taxable_paise/gst_paise
    # are the GST decomposition mirroring ads.campaigns.price_subtotal_paise/
    # price_gst_paise - billing never re-derives them.
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        ForeignKey("billing.ad_orders.id"),
        nullable=True,
        index=True,
    )
    invoice_number: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    taxable_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gst_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PaymentEvent(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "payment_events"
    __table_args__ = ({"schema": "billing"},)

    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="razorpay")
    provider_event_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
