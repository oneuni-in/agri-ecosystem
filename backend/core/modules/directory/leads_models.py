"""Leads engine ORM (D18.B/C): inquiries, responses, DPDP contact-reveal log.

Tables live in the `leads` Postgres schema (spec) but the code lives in
modules/directory: routing needs covers() and get_owned_business(), and the
import-linter independence contract bars a separate module from importing
them. The modules/leads stub remains reserved for E4 intent matchmaking.

business_id / user ids are plain UUIDs (no cross-schema FKs) - validated in
leads_service. ContactReveal is append-only by grant (0020) and must NEVER
gain a phone/contact-value column: it records THAT a reveal happened, not
WHAT was revealed (DPDP alignment).
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, TimestampMixin, UUIDv7PKMixin

inquiry_type_enum = postgresql.ENUM(
    "contact", "milk_subscription", name="inquiry_type", schema="leads", create_type=False
)
inquiry_status_enum = postgresql.ENUM(
    "new", "responded", "closed", name="inquiry_status", schema="leads", create_type=False
)


class Inquiry(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "inquiries"
    __table_args__ = (
        Index("ix_leads_inquiries_business_id_id", "business_id", "id"),
        Index("ix_leads_inquiries_from_user_id_id", "from_user_id", "id"),
        {"schema": "leads"},
    )

    type: Mapped[str] = mapped_column(inquiry_type_enum, nullable=False)
    from_user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True),
        nullable=True,  # NULL = guest submission
    )
    business_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    status: Mapped[str] = mapped_column(inquiry_status_enum, nullable=False, server_default="new")
    pincode: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)


class InquiryResponse(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "responses"
    __table_args__ = (
        Index("ix_leads_responses_inquiry_id_id", "inquiry_id", "id"),
        {"schema": "leads"},
    )

    inquiry_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("leads.inquiries.id"), nullable=False
    )
    business_user_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)


class ContactReveal(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "contact_reveals"
    __table_args__ = (
        Index("ix_leads_contact_reveals_user_id_created_at", "user_id", "created_at"),
        {"schema": "leads"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)


class PincodeInterest(UUIDv7PKMixin, TimestampMixin, Base):
    """Warm empty-state demand capture (D23). Unlike Inquiry this has NO
    business_id — it exists precisely when no vendor covers the pincode
    (tn_no_vendors) or the pincode is non-TN (out_of_area). Feeds seeding
    priority; never routed to a vendor inbox."""

    __tablename__ = "pincode_interest"
    __table_args__ = (
        Index("ix_leads_pincode_interest_pincode_id", "pincode", "id"),
        {"schema": "leads"},
    )

    pincode: Mapped[str] = mapped_column(Text, nullable=False)
    district: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_user_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=True
    )
    milk_type: Mapped[str | None] = mapped_column(Text, nullable=True)
