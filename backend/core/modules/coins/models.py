"""Coins module ORM models (D13) - mirrors migration 0012 exactly.

AgriCoins are NOT money: not purchasable, cashable, or transferable. There is
deliberately no balance-transfer or cash-out column anywhere in this module.
All quantities are integers (BigInteger); floating point is never used.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Integer, Text, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, TimestampMixin, UUIDv7PKMixin

referral_status_enum = postgresql.ENUM(
    "pending", "rewarded", "voided", name="referral_status", schema="coins", create_type=False
)
abuse_status_enum = postgresql.ENUM(
    "open", "reviewed", "voided", name="abuse_status", schema="coins", create_type=False
)


class LedgerEntry(UUIDv7PKMixin, Base):
    """Append-only. Never updated or deleted (DB trigger + revoked grants)."""

    __tablename__ = "ledger_entries"
    __table_args__ = (CheckConstraint("delta <> 0", name="delta_nonzero"), {"schema": "coins"})

    user_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    ref_type: Mapped[str] = mapped_column(Text, nullable=False)
    ref_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )


class Balance(TimestampMixin, Base):
    __tablename__ = "balances"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="balance_nonnegative"),
        {"schema": "coins"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")


class Rule(TimestampMixin, Base):
    __tablename__ = "rules"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"), {"schema": "coins"})

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    daily_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekly_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    valid_from: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=True
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=True
    )


class ReferralCode(TimestampMixin, Base):
    __tablename__ = "referral_codes"
    __table_args__ = {"schema": "coins"}

    user_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class Referral(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "referrals"
    __table_args__ = {"schema": "coins"}

    referrer_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False, index=True
    )
    referee_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False, unique=True
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        referral_status_enum, nullable=False, server_default="pending"
    )
    device_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_prefix: Mapped[str | None] = mapped_column(Text, nullable=True)
    rewarded_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=True
    )
    voided_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=True
    )


class AbuseFlag(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "abuse_flags"
    __table_args__ = {"schema": "coins"}

    referral_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("coins.referrals.id"), nullable=False, index=True
    )
    cluster_reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(abuse_status_enum, nullable=False, server_default="open")
    details: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, nullable=False, server_default="{}"
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=True
    )
