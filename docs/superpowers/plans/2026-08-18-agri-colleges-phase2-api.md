# Agri-colleges Phase 2, Plan 2 — public read API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve the education corpus over the public API of spec §5 — institutions, programmes, student resources and guides — with the trust and status rules of §6 and §7 enforced in the serializer rather than in the handlers.

**Architecture:** Read-only, no writes anywhere. One `SecureRouter` at `/education`, `public=True` on every route, declared in `public_routes.txt` in the same PR. The load-bearing decision is that **a `listed` or non-`active` row cannot emit a fee, a seat count or an admission route** — that suppression lives in one serializer predicate, so no handler can widen it by forgetting a filter. This is the same structural argument as `content.service._published()`.

**Depends on:** Plan 1 (`docs/superpowers/plans/2026-08-17-agri-colleges-phase2-engine.md`) — models, migration `0049` and a populated database. Nothing here touches `apps/`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (async), pytest 8, ruff (line-length 100, `T20` bans bare `print`), mypy.

**Spec:** `docs/superpowers/specs/2026-08-16-agri-colleges-design.md` (§5 public API, §6 surfaces, §7 failure behaviour, §10 gates)

## Global Constraints

- **`public=True` is a two-place declaration.** `scripts/dump_public_routes.py --check` runs in CI (`ci.yml:240`) and fails on any drift between the live registry and `backend/core/public_routes.txt`. Every route added here needs a line in that file, with the comment block explaining *why* it is public — match the prose style of the `/content/feed` and `/market/helplines` entries.
- **No writes.** There is no POST, PUT, PATCH or DELETE in this plan. `app_rt` holds SELECT only on `education.*` (spec §4), so a write handler would fail at runtime anyway — but the point is that none is written.
- **Modules must not import each other.** `modules.education` may import `shared.*` only. `shared.geo` is shared machinery, not another module, so the geo joins are allowed (spec §4, and `market_data` already does this).
- **OFFSET is banned by a lint gate.** Every list is keyset-paginated.
- Ruff line-length **100**; `T20` bans `print`.
- Run `ruff format` and `ruff check --fix` **per task**, not once at the end.
- Commit in logical units. **Do not push** until the owner says "EOD push"; never merge a PR yourself.

## Decisions this plan makes that the spec left open

These are recorded here because a reader of the spec alone would not be able to derive them.

1. **A merged institution does not redirect at the API layer.** `GET /education/institutions/{slug}` for a `status=merged` row returns **200** with `status: "merged"` and `merged_into_slug`, and the *page* issues the 301 (spec §7). An HTTP redirect on a JSON API is a footgun: `fetch` follows redirects by default, so a client asking for `old-slug` would silently receive `new-slug`'s JSON under the URL it requested and have no way to know. Returning the pointer makes the redirect the caller's explicit act.
2. **`?q=` is SQL `ILIKE`, not Meilisearch.** The corpus is ~772 rows against an indexed name column; Meili is for the cross-vertical hub search that Plan 1 Task 4 feeds. Routing the vertical's own filter through Meili would couple this API's availability to the search stack for no measurable gain, and violates the F1 rule (§7) by giving a dead Meili a way to break a college page.
3. **The API owns the state-slug vocabulary.** `geo.states` has `name` and `lgd_code` but **no slug** (verified: `shared/geo/models.py:18-24`). `/colleges/state/[state]` needs a URL segment, so something must slugify. If both the Next.js route generator and the Python filter did it independently, the two would drift on the first state name with a period or an ampersand and the page would 404 against its own link. A single endpoint, `GET /education/states`, returns the slug vocabulary and the frontend consumes it — it never derives one.
4. **`/education/states` returns only states that have at least one institution.** The data audit found 19 states with no agri institution at all. Generating ISR pages for them would publish 19 thin, empty, indexable pages — actively bad for the SEO these pages exist to earn.
5. **List endpoints serve `status=active` only.** A browse list is a list of places a student can apply to. `closed` and `merged` rows stay reachable by direct slug — that is what keeps the 301 and the closed-banner behaviour of §7 working — but they do not appear in listings.
6. **`?district=` resolves inside Tamil Nadu only, today.** `geo.districts` holds 38 rows, all Tamil Nadu, until D65 — so `district_id` stores an LGD code rather than an FK (Plan 1), and a district filter for any other state correctly returns nothing. This is a data gap, not a bug, and the frontend should not offer a district filter outside TN until D65 lands. Plan 3 needs to know this.
7. **`?country=` stays even though every row is `IN`.** The column exists, the filter is three lines, and the corpus scope is an owner decision that could change. Same reasoning the spec already applied to keeping `abroad` in `RESERVED_SLUGS`.

---

### Task 1: Wire shapes and the trust/status suppression gate

**Files:**
- Create: `backend/core/modules/education/schemas.py`
- Create: `backend/core/modules/education/service.py`
- Test: `backend/core/tests/test_education_service.py`

**Interfaces:**
- Consumes: `modules.education.models`, `shared.pagination`, `shared.geo.models`.
- Produces: `InstitutionCard`, `InstitutionDetail`, `InstitutionPage`, `to_card`, `to_detail`; `list_institutions`, `get_institution`, `state_facets`.

- [ ] **Step 1: Write the failing suppression test**

This is the most important test in the plan, so it is written first. It inserts a row that the seed contract would reject — `trust=listed` *with* a fee and a seat count — directly through the ORM, and proves the API shape drops them anyway. If suppression lived in the handler or relied on the seed being clean, this test would fail.

Create `backend/core/tests/test_education_service.py`:

```python
"""education read service: trust and status decide what may be serialized.

The suppression tests deliberately insert rows the seed contract forbids
(rule 10: no seats/fees/admission_route on a `listed` row). That is the
point -- if the only thing stopping a fee reaching a student is that the
CSV happened not to contain one, then a bad import, a hand-fixed row or a
future admin write becomes a correctness bug on a public page. The gate
has to hold against a database that is already wrong.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from modules.education.models import Institution, InstitutionProgramme, Programme
from modules.education.schemas import to_card, to_detail
from modules.education.service import get_institution, list_institutions


async def _inst(session: AsyncSession, slug: str, **kw: object) -> Institution:
    row = Institution(
        slug=slug,
        name_en=kw.pop("name_en", slug.replace("-", " ").title()),
        kind=kw.pop("kind", "affiliated_college"),
        country_code="IN",
        trust=kw.pop("trust", "verified"),
        status=kw.pop("status", "active"),
        source_url="https://example.ac.in/",
        last_verified_at=date(2026, 8, 10),
        **kw,
    )
    session.add(row)
    await session.flush()
    return row


async def _offering(
    session: AsyncSession, inst: Institution, *, seats: int | None, fees: int | None
) -> None:
    programme = Programme(
        slug=f"bsc-ag-{inst.slug}", name_en="B.Sc. Agriculture", level="ug",
        discipline="agriculture", duration_months=48,
    )
    session.add(programme)
    await session.flush()
    session.add(
        InstitutionProgramme(
            institution_id=inst.id, programme_id=programme.id,
            intake_seats=seats, annual_fees_inr=fees,
            admission_route="TNAU counselling",
            source_url="https://example.ac.in/fees", last_verified_at=date(2026, 8, 10),
        )
    )
    await session.flush()


async def test_a_listed_row_cannot_emit_seats_or_fees(db_session: AsyncSession) -> None:
    """The row is poisoned on purpose: seats and fees present, trust=listed."""
    inst = await _inst(db_session, "poisoned-college", trust="listed")
    await _offering(db_session, inst, seats=120, fees=45000)

    detail = to_detail(await get_institution(db_session, "poisoned-college"))  # type: ignore[arg-type]

    assert detail.trust == "listed"
    assert len(detail.programmes) == 1, "the offering itself is still listed"
    offering = detail.programmes[0]
    assert offering.intake_seats is None
    assert offering.annual_fees_inr is None
    assert offering.admission_route is None


async def test_a_closed_verified_row_cannot_emit_admission_data(
    db_session: AsyncSession,
) -> None:
    """Spec section 7: a dead page still saying 'apply here' is the harmful case."""
    inst = await _inst(db_session, "shut-college", trust="verified", status="closed")
    await _offering(db_session, inst, seats=60, fees=30000)

    detail = to_detail(await get_institution(db_session, "shut-college"))  # type: ignore[arg-type]

    assert detail.status == "closed"
    offering = detail.programmes[0]
    assert offering.intake_seats is None
    assert offering.annual_fees_inr is None


async def test_a_verified_active_row_emits_everything(db_session: AsyncSession) -> None:
    """The negative tests above are only meaningful if the positive one passes."""
    inst = await _inst(db_session, "good-college")
    await _offering(db_session, inst, seats=80, fees=25000)

    detail = to_detail(await get_institution(db_session, "good-college"))  # type: ignore[arg-type]

    offering = detail.programmes[0]
    assert offering.intake_seats == 80
    assert offering.annual_fees_inr == 25000
    assert offering.admission_route == "TNAU counselling"


async def test_cards_suppress_on_the_same_predicate_as_details(
    db_session: AsyncSession,
) -> None:
    """Cards and details must not disagree -- a card is where a seat count
    would be most tempting to show and least likely to be reviewed."""
    inst = await _inst(db_session, "card-college", trust="listed")
    card = to_card(inst)
    assert card.trust == "listed"
    assert card.can_show_admission_data is False


async def test_merged_and_closed_rows_stay_out_of_listings(
    db_session: AsyncSession,
) -> None:
    live = await _inst(db_session, "live-college")
    gone = await _inst(db_session, "gone-college", status="closed")
    renamed = await _inst(db_session, "renamed-college", status="merged",
                          merged_into_id=live.id)

    page = await list_institutions(db_session)
    slugs = {row.slug for row in page.items}

    assert "live-college" in slugs
    assert "gone-college" not in slugs
    assert "renamed-college" not in slugs
    # ...but both remain reachable by slug, which is what makes the 301 and
    # the closed banner of spec section 7 possible at all.
    assert await get_institution(db_session, "gone-college") is not None
    assert await get_institution(db_session, "renamed-college") is not None


async def test_verified_rows_sort_before_listed_ones(db_session: AsyncSession) -> None:
    """A student scanning a state page should meet checked entries first."""
    await _inst(db_session, "bulk-a", trust="listed")
    await _inst(db_session, "bulk-b", trust="listed")
    await _inst(db_session, "checked", trust="verified")

    page = await list_institutions(db_session)

    assert page.items[0].slug == "checked"


async def test_the_cursor_walks_the_whole_set_exactly_once(
    db_session: AsyncSession,
) -> None:
    """A compound cursor is where paging bugs live: the rank tie-break has
    to be part of the predicate or rows are dropped at the boundary."""
    for i in range(7):
        await _inst(db_session, f"page-{i}", trust="verified" if i < 3 else "listed")

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):  # bounded: a non-terminating cursor must fail, not hang
        page = await list_institutions(db_session, cursor=cursor, limit=2)
        seen.extend(row.slug for row in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert cursor is None, "paging did not terminate"
    assert len(seen) == len(set(seen)) == 7
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend/core && python -m pytest tests/test_education_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.education.schemas'`

If instead it fails on `modules.education.models`, Plan 1 has not landed. Stop — this plan depends on it.

- [ ] **Step 3: Write the wire shapes**

Create `backend/core/modules/education/schemas.py`:

```python
"""Wire shapes for the education vertical (spec section 5).

One rule shapes this whole file: **a row that has not been checked, or an
institution that no longer runs, must not emit a number a student could
act on.** Seats, fees and admission route are gated on
`can_show_admission_data` -- one predicate, computed once, applied in the
serializer. It is not a handler's job to remember, and it is not the
seed's job either: the gate must hold even when the database is wrong.

`can_show_admission_data` travels ON THE WIRE, so the frontend branches on
one server-computed boolean rather than re-deriving the rule from `trust`
and `status`. A rule re-implemented on the far side of an HTTP boundary is
a rule with two versions.

Institution names are EN-only by deliberate decision (spec section 6): they
are proper nouns, and TA/HI carry only where the institution itself
publishes them. Chrome, eligibility and guide bodies are translated;
`name` is not.
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

    `listed` means the row came from a bulk national directory and was
    never checked against the institution's own page (spec section 6).
    `closed`/`merged` mean the answer would be actively misleading even if
    it was true when recorded (spec section 7).
    """
    return institution.trust == "verified" and institution.status == "active"


class OfferingOut(BaseModel):
    """One programme an institution runs.

    Carries its OWN `source_url`/`last_verified_at`, separate from the
    institution's, so a page can honestly say "college verified Mar 2026 ·
    fees last checked Aug 2025" (spec section 4). A single stamp would let
    a two-year-old fee render under a fresh green badge.
    """

    programme_slug: str
    name: Translated
    level: str
    discipline: str
    duration_months: int | None
    # ── suppressed unless can_show_admission_data ──
    intake_seats: int | None = None
    # int, not Decimal-as-string: fees are whole rupees (Plan 1 records the
    # divergence from the spec's Numeric and why).
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
    # itself never redirects -- see the plan's decision 1.
    merged_into_slug: str | None = None
    parent: RelatedInstitution | None = None
    constituents: list[RelatedInstitution] = []
    programmes: list[OfferingOut] = []


class InstitutionPage(BaseModel):
    items: list[InstitutionCard]
    next_cursor: str | None = None


class StateFacet(BaseModel):
    """The state-slug vocabulary. The frontend consumes these slugs for
    `/colleges/state/[state]`; it never derives one (decision 3)."""

    slug: str
    name: str
    institution_count: int


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
            for child in institution.constituents
        ],
        programmes=[
            _to_offering(row, row.programme, full=full)
            for row in sorted(institution.offerings, key=lambda r: r.programme.slug)
        ],
    )
```

**If the Plan 1 models do not carry `parent`, `constituents`, `merged_into` or `offerings`
relationships**, add them there rather than querying around them here — an N+1 in a
serializer is how a college page with 40 constituent colleges becomes a 41-query request.
Load them eagerly in the service (Step 4), not lazily in the serializer: SQLAlchemy async
raises on implicit lazy load, so a missing `selectinload` fails loudly rather than silently
degrading. That is the good outcome; do not "fix" it by switching the relationship to
`lazy="selectin"` globally, which would make every list query pay for the detail page's joins.

- [ ] **Step 4: Write the read service**

Create `backend/core/modules/education/service.py`:

```python
"""Read-only queries over the education corpus.

There are no writes in this module and no write path to add one to:
`app_rt` holds SELECT only on `education.*` (spec section 4).

Ordering is `(trust_rank, id)` -- verified institutions first, then the
bulk-directory rows, each group in UUIDv7 (import) order. That needs a
two-field keyset cursor, following the `directory/covers.py` precedent.
An id-only cursor would have paged in seed-file order, which is arbitrary,
and buried the checked entries behind hundreds of unchecked ones.
"""

from __future__ import annotations

import base64
import re
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shared.geo.models import District, State
from shared.pagination import DEFAULT_PAGE_SIZE, InvalidCursorError

from .models import Institution, InstitutionProgramme, Programme
from .schemas import InstitutionPage, StateFacet, to_card

if TYPE_CHECKING:  # pragma: no cover
    pass

# verified sorts first; the CASE is reused in the cursor predicate, so it
# is defined once rather than restated at each use site.
_TRUST_RANK = case((Institution.trust == "verified", 0), else_=1)

KINDS = (
    "central_agri_university",
    "state_agri_university",
    "deemed_university",
    "icar_institute",
    "private_university",
    "affiliated_college",
    "constituent_college",
)


class UnknownFilter(ValueError):
    """A filter value outside its enum. 422, not a silent empty page."""


def state_slug(name: str) -> str:
    """The ONE place a state name becomes a URL segment (decision 3).

    `/education/states` publishes what this produces and the `?state=`
    filter resolves through it, so the vocabulary cannot drift between the
    link and the page it points at.
    """
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def encode_institution_cursor(rank: int, last_id: uuid.UUID) -> str:
    raw = f"{rank}:{last_id.hex}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_institution_cursor(cursor: str) -> tuple[int, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        parts = base64.urlsafe_b64decode(padded).decode().split(":")
        if len(parts) != 2:
            raise ValueError(f"expected 2 fields, got {len(parts)}")
        return int(parts[0]), uuid.UUID(hex=parts[1])
    except (ValueError, TypeError) as exc:
        raise InvalidCursorError(f"malformed cursor: {cursor!r}") from exc


def _listable() -> Select[tuple[Institution]]:
    """Active rows only (decision 5).

    Structural, like content's `_published()`: every list query starts
    here, so a handler cannot serve a closed college by forgetting a
    filter. Detail lookups deliberately do NOT use this -- a closed or
    merged institution must stay reachable by slug for the 301 and the
    closed banner of spec section 7.
    """
    return select(Institution).where(Institution.status == "active")


async def list_institutions(
    session: AsyncSession,
    *,
    state: str | None = None,
    district: str | None = None,
    kind: str | None = None,
    is_government: bool | None = None,
    programme: str | None = None,
    country: str | None = None,
    trust: str | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> InstitutionPage:
    query = _listable().options(
        selectinload(Institution.state), selectinload(Institution.district)
    )

    if kind is not None:
        if kind not in KINDS:
            raise UnknownFilter(kind)
        query = query.where(Institution.kind == kind)
    if trust is not None:
        if trust not in ("verified", "listed"):
            raise UnknownFilter(trust)
        query = query.where(Institution.trust == trust)
    if is_government is not None:
        query = query.where(Institution.is_government.is_(is_government))
    if country is not None:
        query = query.where(Institution.country_code == country.upper())
    if state is not None:
        # Resolve through state_slug so the filter speaks the same
        # vocabulary /education/states publishes.
        query = query.join(State, Institution.state_id == State.id).where(
            func.lower(func.regexp_replace(State.name, "[^a-zA-Z0-9]+", "-", "g"))
            == state_slug(state)
        )
    if district is not None:
        # Joins District.lgd_code, NOT District.id: district_id holds the LGD
        # code because geo.districts is Tamil Nadu only until D65 and an FK
        # would reject a valid Punjab college (Plan 1 models.py). Consequence:
        # a district filter outside TN correctly returns nothing, because we
        # do not know those district ids yet. Getting the join column wrong
        # returns nothing too -- which is why the contract suite pins it.
        query = query.join(District, Institution.district_id == District.lgd_code).where(
            func.lower(func.regexp_replace(District.name, "[^a-zA-Z0-9]+", "-", "g"))
            == state_slug(district)
        )
    if programme is not None:
        query = query.where(
            Institution.id.in_(
                select(InstitutionProgramme.institution_id)
                .join(Programme, InstitutionProgramme.programme_id == Programme.id)
                .where(Programme.slug == programme)
            )
        )
    if q is not None:
        # ILIKE, not Meili (decision 2). Escape the wildcards: a user
        # typing "100%" must search for that string, not every row.
        needle = f"%{q.replace('%', r'\%').replace('_', r'\_')}%"
        query = query.where(
            or_(Institution.name_en.ilike(needle), Institution.short_name.ilike(needle))
        )

    if cursor is not None:
        cursor_rank, cursor_id = decode_institution_cursor(cursor)
        # The rank tie-break MUST be part of the predicate. Without the
        # second clause every row sharing the boundary rank is skipped.
        query = query.where(
            or_(
                _TRUST_RANK > cursor_rank,
                (_TRUST_RANK == cursor_rank) & (Institution.id > cursor_id),
            )
        )

    rows = list(
        (await session.scalars(query.order_by(_TRUST_RANK, Institution.id).limit(limit + 1))).all()
    )
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_institution_cursor(0 if last.trust == "verified" else 1, last.id)
    return InstitutionPage(items=[to_card(row) for row in rows], next_cursor=next_cursor)


async def get_institution(session: AsyncSession, slug: str) -> Institution | None:
    """By slug, ANY status -- a closed or merged institution must resolve
    so the page can render its banner or issue its 301 (spec section 7)."""
    query = (
        select(Institution)
        .where(Institution.slug == slug)
        .options(
            selectinload(Institution.state),
            selectinload(Institution.district),
            selectinload(Institution.parent),
            selectinload(Institution.merged_into),
            selectinload(Institution.constituents),
            selectinload(Institution.offerings).selectinload(InstitutionProgramme.programme),
        )
    )
    return await session.scalar(query)


async def state_facets(session: AsyncSession) -> list[StateFacet]:
    """States with at least one active institution, and how many.

    The HAVING is the point (decision 4): 19 states have no agri
    institution at all, and generating an ISR page for each would publish
    19 thin indexable pages with nothing on them.
    """
    query = (
        select(State.name, func.count(Institution.id))
        .join(Institution, Institution.state_id == State.id)
        .where(Institution.status == "active")
        .group_by(State.name)
        .having(func.count(Institution.id) > 0)
        .order_by(State.name)
    )
    return [
        StateFacet(slug=state_slug(name), name=name, institution_count=count)
        for name, count in (await session.execute(query)).all()
    ]
```

**Note on the `regexp_replace` in the state filter.** It mirrors `state_slug()` in SQL so
the comparison can happen in the database rather than by loading all 35 states per request.
The two implementations must agree; Task 4 has a test that walks every row in `geo.states`
and asserts the SQL and Python forms produce the same slug. Do not skip it — this is exactly
the drift decision 3 exists to prevent, reintroduced one layer down.

- [ ] **Step 5: Run the tests**

Run: `cd backend/core && python -m pytest tests/test_education_service.py -v`
Expected: all pass. If `test_the_cursor_walks_the_whole_set_exactly_once` fails with
duplicate or missing slugs, the cursor predicate has lost its tie-break clause.

- [ ] **Step 6: Lint, type-check, commit**

```
cd backend/core
ruff format modules/education/ tests/test_education_service.py
ruff check --fix modules/education/ tests/test_education_service.py
mypy modules/education/
python -m pytest tests/test_education_service.py -q
```

```
git add backend/core/modules/education/schemas.py backend/core/modules/education/service.py \
  backend/core/tests/test_education_service.py
git commit -m "feat(education): read service and wire shapes with a structural trust gate

Seats, fees and admission route are gated on one predicate --
can_show_admission_data = verified AND active -- applied in the serializer,
not in handlers. The tests insert rows the seed contract forbids (listed
WITH a fee) to prove the gate holds against a database that is already
wrong, which is the only version of the gate worth having.

Ordering is (trust_rank, id) on a two-field keyset cursor, following
directory/covers.py. An id-only cursor would page in seed-file order and
bury the checked entries behind hundreds of unchecked ones."
```

---

### Task 2: The institutions router

**Files:**
- Create: `backend/core/modules/education/router.py`
- Modify: `backend/core/main.py` (import and mount)
- Modify: `backend/core/public_routes.txt`
- Test: `backend/core/tests/test_education_router.py`

**Interfaces:**
- Produces: `GET /education/institutions`, `GET /education/institutions/{slug}`, `GET /education/states`.

- [ ] **Step 1: Write the failing router test**

Create `backend/core/tests/test_education_router.py`:

```python
"""education public routes: reachable without auth, and honest about trust."""

from __future__ import annotations

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from modules.education.models import Institution


async def _seed(session: AsyncSession, slug: str, **kw: object) -> Institution:
    row = Institution(
        slug=slug, name_en=kw.pop("name_en", "Test College"),
        kind="affiliated_college", country_code="IN",
        trust=kw.pop("trust", "verified"), status=kw.pop("status", "active"),
        source_url="https://example.ac.in/", last_verified_at=date(2026, 8, 10), **kw,
    )
    session.add(row)
    await session.flush()
    return row


async def test_the_routes_are_public(api: tuple[AsyncClient, AsyncSession]) -> None:
    """No session, no 401 -- a college page is SSR'd for anonymous readers."""
    client, _session = api
    assert (await client.get("/education/institutions")).status_code == 200
    assert (await client.get("/education/states")).status_code == 200


async def test_public_routes_are_registered(api: tuple[AsyncClient, AsyncSession]) -> None:
    """The second half of the two-place declaration. dump_public_routes.py
    --check fails CI if public_routes.txt disagrees with the live app."""
    from main import app

    for path in (
        "/education/institutions",
        "/education/institutions/{slug}",
        "/education/programmes",
        "/education/student-resources",
        "/education/student-resources/{slug}",
        "/education/guides",
        "/education/guides/{slug}",
        "/education/states",
    ):
        assert path in app.state.public_routes, path


async def test_unknown_slug_is_a_real_404(api: tuple[AsyncClient, AsyncSession]) -> None:
    client, _session = api
    response = await client.get("/education/institutions/no-such-college")
    assert response.status_code == 404
    assert response.json()["detail"] == "institution_not_found"


async def test_a_merged_row_returns_200_and_the_pointer_not_a_redirect(
    api: tuple[AsyncClient, AsyncSession],
) -> None:
    """Decision 1: the API hands back the pointer; the PAGE issues the 301.

    A 3xx here would be followed silently by fetch, and the caller would
    receive the successor's JSON under the URL it asked for.
    """
    client, session = api
    target = await _seed(session, "new-name-college")
    await _seed(session, "old-name-college", status="merged", merged_into_id=target.id)
    await session.commit()

    response = await client.get(
        "/education/institutions/old-name-college", follow_redirects=False
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "merged"
    assert body["merged_into_slug"] == "new-name-college"


async def test_a_bad_filter_value_is_422_not_an_empty_page(
    api: tuple[AsyncClient, AsyncSession],
) -> None:
    """An empty 200 tells a caller their filter matched nothing. A wrong
    enum value is a different fact and deserves a different answer."""
    client, _session = api
    response = await client.get("/education/institutions", params={"kind": "hogwarts"})
    assert response.status_code == 422


async def test_a_malformed_cursor_is_422_not_a_500(
    api: tuple[AsyncClient, AsyncSession],
) -> None:
    client, _session = api
    response = await client.get("/education/institutions", params={"cursor": "!!!not-b64!!!"})
    assert response.status_code == 422


async def test_limit_is_bounded(api: tuple[AsyncClient, AsyncSession]) -> None:
    """An unbounded limit is a free full-table scan on a public route."""
    client, _session = api
    assert (await client.get("/education/institutions", params={"limit": 500})).status_code == 422
```

Check the exact name and shape of the API-client fixture before writing this — grep
`tests/conftest.py` for the fixture other router tests use (`test_content_router.py` and
`test_market_alerts.py` both take one) and match it rather than inventing `api`.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend/core && python -m pytest tests/test_education_router.py -v`
Expected: FAIL — 404s on every path, because nothing is mounted yet.

- [ ] **Step 3: Write the router**

Create `backend/core/modules/education/router.py`:

```python
"""Education vertical public reads (spec section 5).

Every route here is `public=True` and declared in
`backend/core/public_routes.txt` in the same PR. They serve reference data
about public institutions -- the same read-only class as
`/catalog/verticals` and `/market/schemes`: no user data, no mutation,
already public at the source, and carrying the source URL and verified-on
date the UI renders.

There is deliberately NO write route, public or private. Rows arrive from a
reviewed seed commit through `scripts/import_education_seed.py`, and
`app_rt` holds SELECT only, so there is no handler to widen.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, InvalidCursorError
from shared.security import SecureRouter

from .schemas import InstitutionDetail, InstitutionPage, StateFacet, to_detail
from .service import (
    KINDS,
    UnknownFilter,
    get_institution,
    list_institutions,
    state_facets,
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

router = SecureRouter(prefix="/education", tags=["education"])

# Slugs are our own vocabulary and bounded on the wire; a filter is a query
# parameter, and an unbounded one invites probing.
_SLUG = Annotated[str | None, Query(max_length=96, pattern=r"^[a-z0-9-]+$")]
_SLUG_PATH = Annotated[str, Path(min_length=1, max_length=96, pattern=r"^[a-z0-9-]+$")]


@router.get("/institutions", public=True)
async def get_institutions(
    session: SessionDep,
    state: _SLUG = None,
    district: _SLUG = None,
    kind: Annotated[str | None, Query(max_length=32)] = None,
    is_government: bool | None = None,
    programme: _SLUG = None,
    country: Annotated[str | None, Query(min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")] = None,
    trust: Annotated[str | None, Query(max_length=16)] = None,
    q: Annotated[str | None, Query(max_length=64)] = None,
    cursor: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> InstitutionPage:
    """Active institutions, verified first (decisions 5 and the ordering note).

    Closed and merged rows are absent by construction -- a browse list is a
    list of places a student can apply to.
    """
    try:
        return await list_institutions(
            session, state=state, district=district, kind=kind,
            is_government=is_government, programme=programme, country=country,
            trust=trust, q=q, cursor=cursor, limit=limit,
        )
    except UnknownFilter as exc:
        raise HTTPException(
            status_code=422, detail=f"unknown filter value {exc.args[0]!r}; kind must be one of "
            f"{', '.join(KINDS)}"
        ) from None
    except InvalidCursorError:
        raise HTTPException(status_code=422, detail="invalid_cursor") from None


@router.get("/institutions/{slug}", public=True)
async def get_institution_detail(session: SessionDep, slug: _SLUG_PATH) -> InstitutionDetail:
    """Any status resolves. A `merged` row answers 200 with
    `merged_into_slug` and the page issues the 301 -- this API never
    redirects (decision 1)."""
    row = await get_institution(session, slug)
    if row is None:
        raise HTTPException(status_code=404, detail="institution_not_found")
    return to_detail(row)


@router.get("/states", public=True)
async def get_states(session: SessionDep) -> list[StateFacet]:
    """The state-slug vocabulary for `/colleges/state/[state]`.

    Uncursored: bounded at ~35 rows by the geo dataset, and a result set
    large enough to need paging would itself be the bug. Only states with
    at least one institution appear (decision 4).
    """
    return await state_facets(session)
```

- [ ] **Step 4: Mount it**

In `backend/core/main.py`, add the import beside the other module routers (keep the
existing alphabetical-by-module grouping):

```python
from modules.education.router import router as education_router
```

and add `education_router` to the list of routers the app includes — find the sequence
containing `directory_router` around line 94 and add it there, preserving the file's
existing ordering convention.

- [ ] **Step 5: Declare the public routes**

Append to `backend/core/public_routes.txt`, matching the prose style of the `/content/feed`
and `/market/helplines` blocks above it:

```
# /education/*: the agri-colleges vertical (spec
# docs/superpowers/specs/2026-08-16-agri-colleges-design.md section 5).
# Public reference data about public institutions -- the same read-only
# class as /catalog/verticals and /market/schemes: no user data, no
# mutation, already public at the source, and carrying the source URL and
# verified-on date the UI renders. There is no write route at all: rows
# arrive from a reviewed seed commit and app_rt holds SELECT only on
# education.*, so there is nothing here for a handler to widen.
#
# Two rules travel on the wire rather than living in the frontend:
# `can_show_admission_data` is computed server-side and suppresses seats,
# fees and admission route for any row that is not both verified and
# active; and /education/states publishes the state-slug vocabulary the
# ISR routes consume, so no slug is ever derived twice.
/education/institutions
/education/institutions/{slug}
/education/states
```

The remaining four paths are added by Task 3, in the same block.

- [ ] **Step 6: Verify the gate agrees**

```
cd backend/core
python scripts/dump_public_routes.py --check
```

Expected: exit 0. A failure prints the drift — the live registry and the file must match
exactly, including the four paths Task 3 has not added yet, so **expect this to fail until
Task 3 lands** and treat that as the reminder it is. If you would rather see it green at
each commit, add all seven paths now and land Task 3 before pushing.

- [ ] **Step 7: Run the tests, lint, type-check, commit**

```
cd backend/core
python -m pytest tests/test_education_router.py -v
ruff format modules/education/ tests/test_education_router.py
ruff check --fix modules/education/ tests/test_education_router.py
mypy modules/education/ main.py
```

`test_public_routes_are_registered` asserts all eight paths and will fail until Task 3 —
that is intentional and is the same reminder as Step 6.

```
git add backend/core/modules/education/router.py backend/core/main.py \
  backend/core/public_routes.txt backend/core/tests/test_education_router.py
git commit -m "feat(education): public institution routes and the state vocabulary

Three routes, all public=True and declared in public_routes.txt in this
same commit -- the gate at scripts/dump_public_routes.py --check fails CI
on any drift between the two.

/education/states exists because geo.states has no slug column. Something
has to turn 'Tamil Nadu' into a URL segment, and if both the Next.js route
generator and the Python filter did it independently they would disagree
on the first state name with a period in it, and the page would 404
against its own link. The API publishes the vocabulary; the frontend
consumes it.

A merged institution answers 200 with merged_into_slug rather than
redirecting. fetch follows 3xx by default, so an API-level redirect would
hand a caller the successor's JSON under the URL it requested, with no
signal that it happened."
```

---

### Task 3: Programmes, student resources and guides

**Files:**
- Modify: `backend/core/modules/education/schemas.py`
- Modify: `backend/core/modules/education/service.py`
- Modify: `backend/core/modules/education/router.py`
- Modify: `backend/core/public_routes.txt`
- Test: `backend/core/tests/test_education_resources.py`

**Interfaces:**
- Produces: `GET /education/programmes`, `/education/student-resources`, `/education/student-resources/{slug}`, `/education/guides`, `/education/guides/{slug}`.

- [ ] **Step 1: Write the failing test**

Create `backend/core/tests/test_education_resources.py`. The invariant that matters here is
the guide `status` gate — a `draft` guide must 404, structurally, the same way an unapproved
content item does:

```python
"""Programmes, scholarships/exams and guides.

The load-bearing test is the draft-guide 404: a guide is written and then
reviewed, and an unreviewed one must not be discoverable by guessing its
slug -- draft, and nonexistent, answer identically.
"""

from __future__ import annotations

from datetime import date

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from modules.education.models import Guide, Programme, StudentResource


async def test_a_draft_guide_404s_exactly_like_a_missing_one(
    api: tuple[AsyncClient, AsyncSession],
) -> None:
    client, session = api
    session.add(
        Guide(
            slug="tn-counselling-2026", title_en="TN Agri Counselling 2026",
            kind="counselling", summary_en="Rounds and dates.",
            steps=[], official_links=["https://tnau.ac.in/"],
            last_verified_at=date(2026, 8, 10), status="draft",
        )
    )
    await session.commit()

    drafted = await client.get("/education/guides/tn-counselling-2026")
    missing = await client.get("/education/guides/no-such-guide")

    assert drafted.status_code == missing.status_code == 404
    assert drafted.json() == missing.json(), "a draft must be indistinguishable from absent"


async def test_draft_guides_are_absent_from_the_index(
    api: tuple[AsyncClient, AsyncSession],
) -> None:
    client, session = api
    session.add(
        Guide(
            slug="draft-guide", title_en="Draft", kind="general", summary_en="x",
            steps=[], official_links=["https://x.gov.in/"],
            last_verified_at=date(2026, 8, 10), status="draft",
        )
    )
    await session.commit()

    body = (await client.get("/education/guides")).json()
    assert all(item["slug"] != "draft-guide" for item in body["items"])


async def test_archived_resources_are_absent_from_the_index(
    api: tuple[AsyncClient, AsyncSession],
) -> None:
    """An expired scholarship listed as live wastes a student's application."""
    client, session = api
    session.add(
        StudentResource(
            slug="dead-scholarship", name_en="Old Scheme", kind="scholarship",
            scope="india", provider="ICAR", official_url="https://icar.org.in/",
            last_verified_at=date(2026, 8, 10), status="archived",
        )
    )
    await session.commit()

    body = (await client.get("/education/student-resources")).json()
    assert all(item["slug"] != "dead-scholarship" for item in body["items"])


async def test_programmes_serve_the_whole_catalog_uncursored(
    api: tuple[AsyncClient, AsyncSession],
) -> None:
    """~47 rows, registry-as-data. A cursor here would be ceremony."""
    client, session = api
    session.add(
        Programme(
            slug="bsc-agriculture", name_en="B.Sc. (Hons.) Agriculture", level="ug",
            discipline="agriculture", duration_months=48,
        )
    )
    await session.commit()

    body = (await client.get("/education/programmes")).json()
    assert any(item["slug"] == "bsc-agriculture" for item in body)


async def test_resource_filters_reject_unknown_enum_values(
    api: tuple[AsyncClient, AsyncSession],
) -> None:
    client, _session = api
    assert (
        await client.get("/education/student-resources", params={"kind": "lottery"})
    ).status_code == 422
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend/core && python -m pytest tests/test_education_resources.py -v`
Expected: FAIL — 404 on every path.

- [ ] **Step 3: Add the shapes**

Append to `schemas.py`: `ProgrammeOut`, `ResourceCard`, `ResourceDetail`, `ResourcePage`,
`GuideCard`, `GuideDetail`, `GuidePage`, and their `to_*` functions. Translated fields
(`name`, `eligibility`, `title`, `summary`) use the `_translated()` helper from Task 1.
`window` and `applies_to` travel as decoded JSON. Every shape carries `official_url` and
`last_verified_at` **non-nullable**, for the same reason `ContentCard` does: a surface
cannot render one of these without saying where it came from and when it was checked.

- [ ] **Step 4: Add the queries**

Append to `service.py`:

```python
def _published_guides() -> Select[tuple[Guide]]:
    """Published only. Structural, like `_listable()` -- the gate is in the
    query builder, not in each handler, so no route can serve a draft by
    forgetting a filter."""
    return select(Guide).where(Guide.status == "published")


def _live_resources() -> Select[tuple[StudentResource]]:
    return select(StudentResource).where(StudentResource.status == "active")
```

then `list_programmes`, `list_resources`, `get_resource`, `list_guides`, `get_guide`.

`get_guide` and `get_resource` **must** start from the gated selects above — unlike
`get_institution`, which deliberately does not, because a closed college still has a page to
render. A draft guide has nothing to render and must be indistinguishable from absent.

Enum validation: `kind` ∈ `{scholarship, exam}`, `category` ∈ `{entrance, recruitment,
language_test}`, `scope` ∈ `{india, international}`, guide `kind` ∈ `{counselling,
foreign_study, general}` — raise `UnknownFilter`, which the router already maps to 422.

Programmes and guides are uncursored: ~47 and ~13 rows, both bounded registries. Resources
are cursored via `paginate()` — the recruitment-exam layer is open-ended (spec §11 owner
action 3) and could grow.

- [ ] **Step 5: Add the routes and declare them**

Five routes on the existing `router`, all `public=True`. Add the remaining four paths to the
`/education/*` block in `public_routes.txt` (`/education/programmes`,
`/education/student-resources`, `/education/student-resources/{slug}`, `/education/guides`,
`/education/guides/{slug}`).

- [ ] **Step 6: Verify the public-route gate is now green**

```
cd backend/core
python scripts/dump_public_routes.py --check
python -m pytest tests/test_education_router.py::test_public_routes_are_registered -v
```

Both must pass now. If `--check` still reports drift, the file and the router disagree on a
path *shape* — usually `{slug}` written as `{guide_slug}` in one place.

- [ ] **Step 7: Lint, type-check, commit**

```
cd backend/core
ruff format modules/education/ tests/test_education_resources.py
ruff check --fix modules/education/ tests/test_education_resources.py
mypy modules/education/
python -m pytest tests/test_education_resources.py tests/test_education_router.py -q
```

```
git add backend/core/modules/education/ backend/core/public_routes.txt \
  backend/core/tests/test_education_resources.py
git commit -m "feat(education): programmes, scholarships/exams and guides

Completes the seven routes of spec section 5; dump_public_routes.py
--check is green again.

Draft guides and archived resources are excluded in the query builders
(_published_guides / _live_resources), not in the handlers, so no route
can serve one by forgetting a filter. get_guide starts from the gated
select and get_institution deliberately does not: a closed college still
has a page to render and a 301 to issue, while a draft guide has nothing
and must be indistinguishable from a slug that was never used.

Programmes and guides are uncursored -- 47 and 13 rows of bounded
registry. Resources are cursored because the recruitment-exam layer is
open-ended."
```

---

### Task 4: The invariants, proven from outside

**Files:**
- Test: `backend/core/tests/test_education_contract.py`

**Interfaces:** none — this task adds no production code. It proves the properties an
implementation could satisfy today and lose next quarter.

- [ ] **Step 1: Write the contract suite**

Create `backend/core/tests/test_education_contract.py`:

```python
"""Properties of the education API that must survive refactoring.

These do not test a function; they test a promise. Each one is a rule that
is cheap to break by accident, expensive to notice, and harmful in
production -- a fee on an unchecked college, a state slug that 404s
against its own link, a write route that appears because someone copied a
router from a module that has one.
"""

from __future__ import annotations

from datetime import date

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.education.service import state_slug
from shared.geo.models import State


async def test_no_education_route_accepts_a_write(
    api: tuple[AsyncClient, AsyncSession],
) -> None:
    """app_rt holds SELECT only on education.*, so a write route would fail
    at runtime anyway. This asserts none was written -- the failure mode is
    someone copying a router from a module that has one."""
    from main import app

    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/education"):
            methods = getattr(route, "methods", set())
            assert methods <= {"GET", "HEAD", "OPTIONS"}, f"{path} accepts {methods}"


async def test_the_sql_and_python_state_slugs_agree_on_every_real_state(
    db_session: AsyncSession,
) -> None:
    """The `?state=` filter slugifies in SQL; /education/states slugifies in
    Python. Decision 3 exists to stop the vocabulary drifting, and this is
    where it would drift back -- one layer down, silently, on the one state
    name with a period or an ampersand in it.

    Walks the real geo dataset, not a sample: the whole risk is the odd
    name nobody thought to write a case for.
    """
    from sqlalchemy import func

    rows = (
        await db_session.execute(
            select(
                State.name,
                func.lower(func.regexp_replace(State.name, "[^a-zA-Z0-9]+", "-", "g")),
            )
        )
    ).all()
    assert rows, "geo.states is empty -- load the geo seed before trusting this test"

    mismatches = [(name, sql) for name, sql in rows if sql.strip("-") != state_slug(name)]
    assert not mismatches, f"SQL and Python slugs disagree: {mismatches}"


async def test_every_state_facet_slug_resolves_to_a_nonempty_filter(
    api: tuple[AsyncClient, AsyncSession],
) -> None:
    """Every slug the API publishes must work as a filter against the API
    that published it. This is the end-to-end version of the test above:
    it would catch a drift the string comparison missed."""
    client, _session = api
    for facet in (await client.get("/education/states")).json():
        page = await client.get("/education/institutions", params={"state": facet["slug"]})
        assert page.status_code == 200, facet
        assert page.json()["items"], f"{facet['slug']} was published with 0 results"


async def test_no_listed_institution_anywhere_in_a_full_page_walk_emits_a_fee(
    api: tuple[AsyncClient, AsyncSession],
) -> None:
    """Walks every institution the list serves and fetches each detail.

    Slow and deliberately exhaustive: `can_show_admission_data` is one
    predicate today, and the day someone adds a second serialization path
    -- a summary endpoint, a sitemap feed, an export -- this is the test
    that notices the fee that came with it.
    """
    client, _session = api
    cursor: str | None = None
    checked = 0
    while True:
        page = (
            await client.get(
                "/education/institutions",
                params={"limit": 100, **({"cursor": cursor} if cursor else {})},
            )
        ).json()
        for card in page["items"]:
            if card["can_show_admission_data"]:
                continue
            detail = (await client.get(f"/education/institutions/{card['slug']}")).json()
            for offering in detail["programmes"]:
                assert offering["intake_seats"] is None, card["slug"]
                assert offering["annual_fees_inr"] is None, card["slug"]
                assert offering["admission_route"] is None, card["slug"]
            checked += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break
    # Not asserting checked > 0: a fixture set with no listed rows is a
    # valid state, and a test that demands one would fail for the wrong
    # reason. The walk is the assertion.
    assert checked >= 0


async def test_the_ilike_search_treats_wildcards_as_text(
    api: tuple[AsyncClient, AsyncSession],
) -> None:
    """A user typing '%' must search for that character, not match every
    row. Unescaped, `q=%` returns the entire corpus."""
    client, session = api
    from modules.education.models import Institution

    session.add(
        Institution(
            slug="plain-college", name_en="Plain College", kind="affiliated_college",
            country_code="IN", trust="verified", status="active",
            source_url="https://x.ac.in/", last_verified_at=date(2026, 8, 10),
        )
    )
    await session.commit()

    body = (await client.get("/education/institutions", params={"q": "%"})).json()
    assert body["items"] == [], "an unescaped LIKE wildcard leaked the whole corpus"


async def test_a_dead_database_does_not_500_the_list(
    api: tuple[AsyncClient, AsyncSession],
) -> None:
    """F1 (spec section 7): a dead education engine never 500s a page.

    NOTE: verify how the app's other public reads behave here before
    asserting -- if the shared session dependency already turns a
    connection failure into a 503, assert that instead of writing a new
    swallow-everything handler. The rule is that the SECTION degrades, and
    that is enforced on the page, not necessarily in this API. If the
    honest answer is that F1 lives entirely in the frontend, delete this
    test and say so in the commit message rather than leaving a test that
    asserts nothing.
    """
```

Note the last test is written as an open question on purpose. Resolve it during
implementation — either it asserts something real, or it is deleted with a one-line note.
Do not leave it as a body-less placeholder.

- [ ] **Step 2: Run the suite**

Run: `cd backend/core && python -m pytest tests/test_education_contract.py -v`

`test_the_sql_and_python_state_slugs_agree_on_every_real_state` needs the geo dataset
loaded. If it reports `geo.states is empty`, run the geo loader first
(`python scripts/load_geo.py`) — a recreated volume needs it, and an empty geo table makes
this test pass vacuously, which is worse than failing.

- [ ] **Step 3: Fix what it finds, then commit**

If the SQL/Python slug test fails, fix `state_slug()` and the SQL expression **together**,
and add the offending state name to the test as a named case so the regression has a name.

```
git add backend/core/tests/test_education_contract.py backend/core/modules/education/
git commit -m "test(education): the API's invariants, proven from outside

Five properties that are cheap to break and expensive to notice: no write
route exists; the SQL and Python state slugs agree on every real state
name; every published facet slug resolves to a nonempty filter; no
non-verified institution emits a fee anywhere in a full page walk; and a
LIKE wildcard typed by a user is text, not a wildcard.

The full-corpus walk is deliberately slow. can_show_admission_data is one
predicate today; the day a second serialization path appears -- a summary
endpoint, a sitemap feed, an export -- this is what notices the fee that
came with it."
```

---

### Task 5: Spec amendment and hand-off

**Files:**
- Modify: `docs/superpowers/specs/2026-08-16-agri-colleges-design.md`
- Modify: `docs/qa/agri-acceptance-checklist.md`

- [ ] **Step 1: Record `/education/states` in the spec**

§5 lists seven routes; this plan ships eight. Add the route to the §5 block and, beneath it,
a short amendment note in the style of the §6 India-only note:

> **Amended 18 Aug 2026.** `GET /education/states` added. `geo.states` has no slug column,
> so the `/colleges/state/[state]` segment has to be derived from the state name. Deriving
> it in both the Next.js route generator and the Python filter would let the two drift on
> the first name with a period or an ampersand, and the page would 404 against its own
> link. The API publishes the vocabulary and the frontend consumes it. Only states with at
> least one institution are returned — 19 states have none, and ISR pages for them would
> be thin indexable pages with nothing on them.

Also record decisions 1 (no API-level redirect) and 2 (`q=` is ILIKE, not Meili) in §7 and
§5 respectively — both are behaviour a reader of the spec would otherwise guess wrong.

- [ ] **Step 2: Add the acceptance rows**

Add to `docs/qa/agri-acceptance-checklist.md`, matching the existing row format:

- a `listed` college page shows no fee, no seat count and no admission route
- a closed college page shows its banner, no admission data, and returns 200
- a renamed college's old URL lands on its successor
- every state page linked from the state index has at least one college on it

These are the four a human can check in a browser in two minutes, and they are the four that
would embarrass us. The rest is covered by the contract suite.

- [ ] **Step 3: Commit**

```
git add docs/superpowers/specs/2026-08-16-agri-colleges-design.md \
  docs/qa/agri-acceptance-checklist.md
git commit -m "docs(education): record the states route and the two API decisions

Spec section 5 listed seven routes; the API ships eight. /education/states
exists because geo.states has no slug column and something has to turn
'Tamil Nadu' into a URL segment -- doing it on both sides of the HTTP
boundary is how a link 404s against the page it points at.

Also records the two decisions a reader would otherwise guess wrong: the
API returns 200 with a pointer for a merged institution rather than
redirecting, and ?q= is SQL ILIKE rather than Meilisearch, so a dead
search stack cannot break a college page."
```

---

## What this plan deliberately does NOT do

- **No `apps/` work.** Routes, ISR, JSON-LD, the trust badge, sitemap entries and the
  registry flip are Plan 3. That is what keeps this mergeable before A-U4.
- **No admin surface.** There is no moderation queue for education because there is no
  user-generated row. Editing a college means editing a CSV and opening a PR, which is the
  reviewable path the read-only grant was chosen to force.
- **No Meili query path.** Hub search is fed by Plan 1 Task 4's fat events; this API does
  not read Meili at all.
- **No freshness surfacing.** `scripts/education_freshness.py` (Plan 1 Task 5) reports stale
  stamps to an operator. Deciding what a stale stamp should do to a *page* is a product
  question for Plan 3.

## Hand-off to Plan 3

Plan 3 (surfaces) can rely on:

- `can_show_admission_data` on every card and detail — branch on it, never re-derive it from
  `trust` and `status`.
- `/education/states` as the sole source of state slugs for `generateStaticParams`.
- `status` + `merged_into_slug` on the detail shape as the inputs to the 301 and the closed
  banner. **The API does not redirect; the page must.**
- `trust == "verified"` as the `noindex` decision input, and the same field driving whether a
  row enters the sitemap feed.
- Both `source_url`/`last_verified_at` pairs — institution-level and per-offering — for the
  "verified Mar 2026 · fees last checked Aug 2025" line.

Plan 3 must also know that **`?district=` only works in Tamil Nadu** until D65 loads the
rest of `geo.districts` — offering the filter elsewhere would render an empty result set that
looks like "no colleges here" rather than "we do not have that data".

Open question Plan 3 must answer: **what a `verified` institution with a stale offering stamp
renders.** The data says "checked, but the fee is a year old". The options are showing it
with the date, hiding the number and keeping the programme, or hiding both. This is a product
call, not an engineering one, and it belongs with the owner.
