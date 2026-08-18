"""Wire shapes for the education vertical (spec section 5).

One rule shapes this whole file: **a row that has not been checked, or an
institution that no longer runs, must not emit a number a student could act
on.** Seats, fees and admission route are gated on `can_show_admission_data`
— one predicate, computed once, applied in the serializer. It is not a
handler's job to remember, and it is not the seed's job either: the gate must
hold even when the database is wrong.

`can_show_admission_data` travels ON THE WIRE, so the frontend branches on one
server-computed boolean rather than re-deriving the rule from `trust` and
`status`. A rule re-implemented on the far side of an HTTP boundary is a rule
with two versions.

Institution names render EN-only by deliberate decision (spec section 6): they
are proper nouns, and TA/HI carry only where the institution itself publishes
them. Chrome, eligibility and guide bodies are translated; `name` is not.
"""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel

from .models import Guide, Institution, InstitutionProgramme, Programme, StudentResource

# Locale maps travel whole so the client picks with its own fallback rule,
# matching content's Translated and market_data's TranslatedText.
Translated = dict[str, str]


def _translated(**parts: str | None) -> Translated:
    return {locale: value for locale, value in parts.items() if value}


def can_show_admission_data(institution: Institution) -> bool:
    """Seats, fees and admission route are publishable only for a checked
    institution that is still running.

    `listed` means the row came from a bulk national directory and was never
    checked against the institution's own page (spec section 6).
    `closed`/`merged` mean the answer would be actively misleading even if it
    was true when recorded (spec section 7).
    """
    return institution.trust == "verified" and institution.status == "active"


class OfferingOut(BaseModel):
    """One programme an institution runs.

    Carries its OWN `source_url`/`last_verified_at`, separate from the
    institution's, so a page can honestly say "college verified Mar 2026 ·
    fees last checked Aug 2025" (spec section 4). A single stamp would let a
    two-year-old fee render under a fresh green badge.
    """

    programme_slug: str
    name: Translated
    level: str
    discipline: str
    duration_months: int | None
    # ── suppressed unless can_show_admission_data ──
    intake_seats: int | None = None
    # int, not Decimal-as-string: fees are whole rupees (see models.py).
    annual_fees_inr: int | None = None
    fee_note: str | None = None
    admission_route: str | None = None
    # ── stamps: present whenever the offering is ──
    source_url: str | None = None
    last_verified_at: date | None = None


class InstitutionCard(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    short_name: str | None
    kind: str
    is_government: bool | None
    state: str | None
    district: str | None
    country_code: str
    website: str | None
    established_year: int | None
    trust: str
    status: str
    last_verified_at: date
    can_show_admission_data: bool


class RelatedInstitution(BaseModel):
    slug: str
    name: str
    kind: str


class InstitutionDetail(InstitutionCard):
    name_ta: str | None = None
    name_hi: str | None = None
    address: str | None = None
    pincode: str | None = None
    lat: str | None = None
    lng: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    accreditation: dict[str, object] | None = None
    source_url: str
    # `merged` rows carry the pointer the PAGE turns into a 301. The API
    # itself never redirects: fetch follows 3xx by default, so a caller would
    # silently receive the successor's JSON under the URL it asked for.
    merged_into_slug: str | None = None
    parent: RelatedInstitution | None = None
    constituents: list[RelatedInstitution] = []
    programmes: list[OfferingOut] = []


class InstitutionPage(BaseModel):
    items: list[InstitutionCard]
    next_cursor: str | None = None


class StateFacet(BaseModel):
    """The state-slug vocabulary. The frontend consumes these slugs for
    `/colleges/state/[state]`; it never derives one."""

    slug: str
    name: str
    institution_count: int


class ProgrammeOut(BaseModel):
    slug: str
    name: Translated
    level: str
    discipline: str
    duration_months: int | None
    description: Translated


class ResourceCard(BaseModel):
    """A scholarship or an exam.

    `official_url` and `last_verified_at` are NON-nullable, for the same
    reason ContentCard's attribution is: a surface cannot render one of these
    without saying where it came from and when it was checked.
    """

    id: uuid.UUID
    slug: str
    name: Translated
    kind: str
    category: str | None
    scope: str
    provider: str | None
    levels: list[str]
    benefit: str | None
    window: dict[str, object] | None
    official_url: str
    last_verified_at: date


class ResourceDetail(ResourceCard):
    eligibility: Translated = {}
    applies_to: dict[str, object] | None = None


class ResourcePage(BaseModel):
    items: list[ResourceCard]
    next_cursor: str | None = None


class GuideCard(BaseModel):
    id: uuid.UUID
    slug: str
    title: Translated
    kind: str
    country_code: str | None
    state: str | None
    summary: Translated
    last_verified_at: date


class GuideDetail(GuideCard):
    # Ordered {title, body, links}. Rendered in order; the order is the guide.
    steps: list[dict[str, object]] = []
    # A flat list of URL strings, matching official_links_json in the seed --
    # NOT a list of {label, url} objects.
    official_links: list[str] = []


def to_card(institution: Institution) -> InstitutionCard:
    return InstitutionCard(
        id=institution.id,
        slug=institution.slug,
        name=institution.name_en,
        short_name=institution.short_name,
        kind=institution.kind,
        is_government=institution.is_government,
        state=institution.state.name if institution.state is not None else None,
        district=institution.district.name if institution.district is not None else None,
        country_code=institution.country_code,
        website=institution.website,
        established_year=institution.established_year,
        trust=institution.trust,
        status=institution.status,
        last_verified_at=institution.last_verified_at,
        can_show_admission_data=can_show_admission_data(institution),
    )


def _to_offering(row: InstitutionProgramme, programme: Programme, *, full: bool) -> OfferingOut:
    out = OfferingOut(
        programme_slug=programme.slug,
        name=_translated(en=programme.name_en, ta=programme.name_ta, hi=programme.name_hi),
        level=programme.level,
        discipline=programme.discipline,
        duration_months=programme.duration_months,
        source_url=row.source_url,
        last_verified_at=row.last_verified_at,
    )
    if not full:
        # Deliberately returns the offering, minus the actionable numbers:
        # "this college runs B.Sc. Agriculture" is true and useful; "it has
        # 120 seats at Rs 45,000" is a claim we have not checked.
        return out
    out.intake_seats = row.intake_seats
    out.annual_fees_inr = row.annual_fees_inr
    out.fee_note = row.fee_note
    out.admission_route = row.admission_route
    return out


def to_detail(institution: Institution) -> InstitutionDetail:
    full = can_show_admission_data(institution)
    card = to_card(institution)
    return InstitutionDetail(
        **card.model_dump(),
        name_ta=institution.name_ta,
        name_hi=institution.name_hi,
        address=institution.address,
        pincode=institution.pincode,
        lat=str(institution.lat) if institution.lat is not None else None,
        lng=str(institution.lng) if institution.lng is not None else None,
        contact_phone=institution.contact_phone,
        contact_email=institution.contact_email,
        accreditation=institution.accreditation,
        source_url=institution.source_url,
        merged_into_slug=(
            institution.merged_into.slug if institution.merged_into is not None else None
        ),
        parent=(
            RelatedInstitution(
                slug=institution.parent.slug,
                name=institution.parent.name_en,
                kind=institution.parent.kind,
            )
            if institution.parent is not None
            else None
        ),
        constituents=[
            RelatedInstitution(slug=child.slug, name=child.name_en, kind=child.kind)
            for child in sorted(institution.constituents, key=lambda c: c.name_en)
        ],
        programmes=[
            _to_offering(row, row.programme, full=full)
            for row in sorted(institution.offerings, key=lambda r: r.programme.slug)
        ],
    )


def to_programme(row: Programme) -> ProgrammeOut:
    return ProgrammeOut(
        slug=row.slug,
        name=_translated(en=row.name_en, ta=row.name_ta, hi=row.name_hi),
        level=row.level,
        discipline=row.discipline,
        duration_months=row.duration_months,
        description=_translated(
            en=row.description_en, ta=row.description_ta, hi=row.description_hi
        ),
    )


def _levels(raw: str | None) -> list[str]:
    """`levels` is comma-separated in the CSV and stored verbatim."""
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def to_resource_card(row: StudentResource) -> ResourceCard:
    return ResourceCard(
        id=row.id,
        slug=row.slug,
        name=_translated(en=row.name_en, ta=row.name_ta, hi=row.name_hi),
        kind=row.kind,
        category=row.category,
        scope=row.scope,
        provider=row.provider,
        levels=_levels(row.levels),
        benefit=row.benefit,
        window=row.window,
        official_url=row.official_url,
        last_verified_at=row.last_verified_at,
    )


def to_resource_detail(row: StudentResource) -> ResourceDetail:
    return ResourceDetail(
        **to_resource_card(row).model_dump(),
        eligibility=_translated(
            en=row.eligibility_en, ta=row.eligibility_ta, hi=row.eligibility_hi
        ),
        applies_to=row.applies_to,
    )


def to_guide_card(row: Guide, state_name: str | None) -> GuideCard:
    return GuideCard(
        id=row.id,
        slug=row.slug,
        title=_translated(en=row.title_en, ta=row.title_ta, hi=row.title_hi),
        kind=row.kind,
        country_code=row.country_code,
        state=state_name,
        summary=_translated(en=row.summary_en, ta=row.summary_ta, hi=row.summary_hi),
        last_verified_at=row.last_verified_at,
    )


def to_guide_detail(row: Guide, state_name: str | None) -> GuideDetail:
    return GuideDetail(
        **to_guide_card(row, state_name).model_dump(),
        steps=list(row.steps or []),
        official_links=list(row.official_links or []),
    )
