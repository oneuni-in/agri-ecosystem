"""Billing ORM models (D20). Money-in only: subscriptions + invoices + the
raw (scrubbed) webhook log. No card/instrument data ever lands here -
Razorpay hosted flows hold the instrument; we store provider ids and
amounts only. payment_events is append-only by grant (0021)."""

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


class Invoice(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "status IN ('issued', 'paid', 'failed', 'void')", name="invoices_status_check"
        ),
        {"schema": "billing"},
    )

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        ForeignKey("billing.subscriptions.id"),
        nullable=False,
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


class PaymentEvent(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "payment_events"
    __table_args__ = ({"schema": "billing"},)

    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="razorpay")
    provider_event_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
