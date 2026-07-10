"""Identity module ORM models (D06.A/D) - mirrors migration 0007 exactly.

Every model rides the D03 mixins. The internal UUIDv7 PK is server-side
forever: it must never appear in a URL, API response, or INFO log. The public
identity is users.agri_id (@handle or AG-XXXXXXX fallback) - the
serialization guard in schemas.py makes leaking structurally impossible.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, SoftDeleteMixin, TimestampMixin, UUIDv7PKMixin

user_status_enum = postgresql.ENUM(
    "active", "suspended", "deleted", name="user_status", schema="identity", create_type=False
)
user_language_enum = postgresql.ENUM(
    "en", "ta", "hi", name="user_language", schema="identity", create_type=False
)

# user_id FK columns are written out per model rather than through a helper:
# mapped_column() is a dataclass_transform field specifier, and mypy only
# recognizes it when called directly in the class body.


class User(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "identity"}

    phone: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    phone_verified_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        user_status_enum, server_default=text("'active'"), nullable=False
    )
    agri_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    agri_id_changed_once: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )


class HandleHistory(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "handles_history"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    old_agri_id: Mapped[str] = mapped_column(Text, nullable=False)
    new_agri_id: Mapped[str] = mapped_column(Text, nullable=False)


class OtpRequest(UUIDv7PKMixin, TimestampMixin, Base):
    """Stores the OTP code HASH only - a plaintext code column must never exist."""

    __tablename__ = "otp_requests"
    __table_args__ = {"schema": "identity"}

    phone: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)


class SessionRefresh(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "sessions_refresh"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    device_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    rotated_from: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.sessions_refresh.id"), nullable=True
    )


class Email(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "emails"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class Role(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": "identity"}

    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Permission(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "permissions"
    __table_args__ = {"schema": "identity"}

    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class RolePermission(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id"),
        {"schema": "identity"},
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.roles.id"), nullable=False
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.permissions.id"), nullable=False
    )


class UserRole(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id"),
        {"schema": "identity"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.roles.id"), nullable=False
    )


class Profile(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "profiles"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, unique=True
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    district: Mapped[str | None] = mapped_column(Text, nullable=True)
    pincode: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(
        user_language_enum, server_default=text("'en'"), nullable=False
    )
    interests: Mapped[list[str]] = mapped_column(
        postgresql.JSONB, server_default=text("'[]'::jsonb"), nullable=False
    )
    completion_score: Mapped[int] = mapped_column(
        Integer, server_default=text("0"), nullable=False
    )


class Address(UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "addresses"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, index=True
    )
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    line1: Mapped[str] = mapped_column(Text, nullable=False)
    line2: Mapped[str | None] = mapped_column(Text, nullable=True)
    district: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    pincode: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )


class Preference(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "preferences"
    __table_args__ = {"schema": "identity"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False, unique=True
    )
    notifications: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    privacy: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
