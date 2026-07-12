"""Notify module ORM (D12): templates / notifications / deliveries / preferences."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, TimestampMixin, UUIDv7PKMixin

_channel = postgresql.ENUM(
    "in_app", "sms", "email", name="notify_channel", schema="notify", create_type=False
)
_status = postgresql.ENUM(
    "pending", "sent", "failed", "dead", name="delivery_status", schema="notify", create_type=False
)
_locale = postgresql.ENUM(
    "en", "ta", "hi", name="notify_locale", schema="notify", create_type=False
)


class Template(UUIDv7PKMixin, TimestampMixin, Base):
    """Message template; body uses {var} placeholders (modules/notify/rendering.py)."""

    __tablename__ = "templates"
    __table_args__ = (
        UniqueConstraint("key", "channel", "locale"),
        {"schema": "notify"},
    )

    key: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(_channel, nullable=False)
    locale: Mapped[str] = mapped_column(_locale, nullable=False)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)  # email only
    body: Mapped[str] = mapped_column(Text, nullable=False)


class Notification(UUIDv7PKMixin, TimestampMixin, Base):
    """One user-visible in-app notification; body renders at read time."""

    __tablename__ = "notifications"
    __table_args__ = {"schema": "notify"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False, index=True
    )
    template_key: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False, default=dict)
    locale: Mapped[str] = mapped_column(_locale, nullable=False, server_default="en")
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class Delivery(UUIDv7PKMixin, TimestampMixin, Base):
    """One channel-send attempt trail for a notification. destination is the
    address this delivery goes to; it is stored for retry, NEVER logged."""

    __tablename__ = "deliveries"
    __table_args__ = {"schema": "notify"}

    notification_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        ForeignKey("notify.notifications.id"),
        nullable=False,
        index=True,
    )
    channel: Mapped[str] = mapped_column(_channel, nullable=False)
    status: Mapped[str] = mapped_column(_status, nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    destination: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Preference(UUIDv7PKMixin, TimestampMixin, Base):
    """Per-user channel opt-out rows; absence of a row means enabled.
    in_app is not toggleable (router rejects it)."""

    __tablename__ = "preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "channel"),
        {"schema": "notify"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(_channel, nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, server_default="true")
