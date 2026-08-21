"""Erasure requests (ID-U1 W4, DPDP 2023).

Deletion is a SOFT flow on purpose. A person who taps "delete my AgriID" gets
a grace period in which the request can be withdrawn, because the action is
irreversible and the tap is one tap. Only after the grace does a job actually
erase, and only if nothing is holding it.

The row is the audit trail: who asked, when, what held it, when it ran. It
outlives the user's own data by design - after erasure the row keeps the
request's *shape* (dates, status, reasons) and nothing that identifies a
person beyond the FK, so "we did erase this account, on this date" remains
answerable to a regulator.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, TimestampMixin, UUIDv7PKMixin

# pending  - inside the grace window, withdrawable by the user
# held     - grace elapsed but a module reported a reason not to proceed
# executed - erasers ran
# cancelled- the user changed their mind, or staff released it
ERASURE_STATUSES = ("pending", "held", "executed", "cancelled")


class ErasureRequest(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "erasure_requests"
    __table_args__ = (
        # the admin queue reads by status, newest first
        Index("ix_identity_erasure_requests_status_created", "status", "created_at"),
        # one OPEN request per user is enforced in the service, not here: a
        # partial unique index would also block the historical rows this
        # table exists to keep.
        Index("ix_identity_erasure_requests_user", "user_id"),
        {"schema": "identity"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    # when the grace window ends and the job may act
    execute_after: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=False
    )
    # comma-joined "module:reason" strings from shared.dpdp.erasure_holds.
    # Staff-facing only; the user is told their request is under review, not
    # which module objected and why.
    hold_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True), nullable=True
    )
    # who closed it, when staff did: NULL means the user withdrew it
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=True
    )
