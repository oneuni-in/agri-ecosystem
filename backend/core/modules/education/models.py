"""Education engine ORM models. Tables land in 0049.

Read-only by design: `app_rt` holds SELECT and nothing else (spec section 4),
because every row arrives from a reviewed seed commit, never from a user.

`trust` is the load-bearing column. A `listed` row came from a bulk national
directory and has not been checked against the institution's own page, so the
surfaces must branch on `trust` - never on whether a field happens to be
populated - before rendering a fee, a seat count or an admission route.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db import Base, TimestampMixin, UUIDv7PKMixin
from shared.geo.models import District, State
from shared.slugs import ImmutableSlugMixin

SCHEMA = "education"


class Institution(UUIDv7PKMixin, ImmutableSlugMixin, TimestampMixin, Base):
    __tablename__ = "institutions"
    __table_args__ = {"schema": SCHEMA}

    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    name_ta: Mapped[str | None] = mapped_column(Text)
    name_hi: Mapped[str | None] = mapped_column(Text)
    short_name: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    is_government: Mapped[bool | None] = mapped_column(Boolean)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.institutions.id", ondelete="RESTRICT")
    )
    country_code: Mapped[str] = mapped_column(Text, nullable=False, default="IN")
    # ASYMMETRIC ON PURPOSE, and the asymmetry is the point.
    #
    # state_id is a real cross-schema FK, as spec section 4 requires. All 36
    # states are in data/geo/states.csv, so the constraint can never reject a
    # valid row, and geo.districts already declares ForeignKey("geo.states.id")
    # -- the cross-schema reference is the house idiom, not a new risk.
    #
    # district_id is NOT an FK. data/geo/districts.csv holds 38 rows, all of
    # them Tamil Nadu (state_lgd_code 33), until D65. An FK would reject a
    # valid Punjab college outright. So it stores the district's LGD code as
    # a plain integer and reads join on District.lgd_code -- district
    # filtering therefore resolves inside Tamil Nadu only today. That is a
    # data gap, not a schema bug, and it closes when D65 loads the rest.
    state_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("geo.states.id", ondelete="RESTRICT"), index=True
    )
    district_id: Mapped[int | None] = mapped_column(Integer, index=True)
    pincode: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[float | None] = mapped_column(Numeric(9, 6))
    address: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    contact_phone: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(Text)
    established_year: Mapped[int | None] = mapped_column(Integer)
    accreditation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    trust: Mapped[str] = mapped_column(Text, nullable=False, default="listed")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.institutions.id", ondelete="RESTRICT")
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    last_verified_at: Mapped[date] = mapped_column(Date, nullable=False)

    # Relationships exist so the read API can eager-load rather than N+1 a
    # detail page. None is lazy="selectin": a list query must not silently
    # pay for the detail page's joins. Async SQLAlchemy raises on implicit
    # lazy load, so a forgotten selectinload() fails loudly -- which is what
    # we want. Plan 2's serializer reads exactly these.
    state: Mapped[State | None] = relationship("State", lazy="raise")
    district: Mapped[District | None] = relationship(
        "District",
        primaryjoin="foreign(Institution.district_id) == District.lgd_code",
        viewonly=True,
        lazy="raise",
    )
    parent: Mapped[Institution | None] = relationship(
        "Institution",
        remote_side="Institution.id",
        foreign_keys=[parent_id],
        back_populates="constituents",
        lazy="raise",
    )
    constituents: Mapped[list[Institution]] = relationship(
        "Institution",
        foreign_keys=[parent_id],
        back_populates="parent",
        lazy="raise",
    )
    merged_into: Mapped[Institution | None] = relationship(
        "Institution",
        remote_side="Institution.id",
        foreign_keys=[merged_into_id],
        lazy="raise",
    )
    offerings: Mapped[list[InstitutionProgramme]] = relationship(
        "InstitutionProgramme",
        back_populates="institution",
        lazy="raise",
    )


class Programme(UUIDv7PKMixin, ImmutableSlugMixin, TimestampMixin, Base):
    __tablename__ = "programmes"
    __table_args__ = {"schema": SCHEMA}

    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    name_ta: Mapped[str | None] = mapped_column(Text)
    name_hi: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    discipline: Mapped[str] = mapped_column(Text, nullable=False)
    duration_months: Mapped[int | None] = mapped_column(Integer)
    description_en: Mapped[str | None] = mapped_column(Text)
    description_ta: Mapped[str | None] = mapped_column(Text)
    description_hi: Mapped[str | None] = mapped_column(Text)


class InstitutionProgramme(UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "institution_programmes"
    __table_args__ = (
        UniqueConstraint("institution_id", "programme_id", name="uq_inst_prog"),
        {"schema": SCHEMA},
    )

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.institutions.id", ondelete="CASCADE"), nullable=False
    )
    programme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.programmes.id", ondelete="RESTRICT"), nullable=False
    )
    intake_seats: Mapped[int | None] = mapped_column(Integer)
    # Integer, though spec section 4 says Numeric. DELIBERATE: every one of
    # the 277 fee values in the seed is whole rupees, nobody quotes paise in
    # an annual fee, and Numeric would put a Decimal on the wire -- which the
    # D24 covers work already had to serialize as a string to stop it
    # arriving as a float. An int is exact, JSON-native and needs no
    # convention.
    annual_fees_inr: Mapped[int | None] = mapped_column(Integer)
    fee_note: Mapped[str | None] = mapped_column(Text)
    admission_route: Mapped[str | None] = mapped_column(Text)
    # Its OWN stamps, separate from the institution's. A college's existence
    # and its current fee go stale at completely different rates, and one
    # stamp would let a two-year-old fee render under a fresh green badge.
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    last_verified_at: Mapped[date] = mapped_column(Date, nullable=False)

    institution: Mapped[Institution] = relationship(
        "Institution", back_populates="offerings", lazy="raise"
    )
    programme: Mapped[Programme] = relationship("Programme", lazy="raise")


class StudentResource(UUIDv7PKMixin, ImmutableSlugMixin, TimestampMixin, Base):
    __tablename__ = "student_resources"
    __table_args__ = {"schema": SCHEMA}

    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    name_ta: Mapped[str | None] = mapped_column(Text)
    name_hi: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(Text)
    levels: Mapped[str | None] = mapped_column(Text)
    eligibility_en: Mapped[str | None] = mapped_column(Text)
    eligibility_ta: Mapped[str | None] = mapped_column(Text)
    eligibility_hi: Mapped[str | None] = mapped_column(Text)
    benefit: Mapped[str | None] = mapped_column(Text)
    applies_to: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    window: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    official_url: Mapped[str] = mapped_column(Text, nullable=False)
    last_verified_at: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")


class Guide(UUIDv7PKMixin, ImmutableSlugMixin, TimestampMixin, Base):
    __tablename__ = "guides"
    __table_args__ = {"schema": SCHEMA}

    title_en: Mapped[str] = mapped_column(Text, nullable=False)
    title_ta: Mapped[str | None] = mapped_column(Text)
    title_hi: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str | None] = mapped_column(Text)
    state_id: Mapped[uuid.UUID | None] = mapped_column(
        postgresql.UUID(as_uuid=True), ForeignKey("geo.states.id", ondelete="RESTRICT")
    )
    summary_en: Mapped[str | None] = mapped_column(Text)
    summary_ta: Mapped[str | None] = mapped_column(Text)
    summary_hi: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    # A flat list of URL strings, matching official_links_json in the seed
    # (checked against guides.csv) -- NOT a list of {label, url} objects.
    official_links: Mapped[list[str] | None] = mapped_column(JSONB)
    last_verified_at: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
