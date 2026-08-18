"""Read-only queries over the education corpus.

There are no writes in this module and no write path to add one to: `app_rt`
holds SELECT only on `education.*` (spec section 4, migration 0049).

Institution ordering is `(trust_rank, id)` — verified institutions first, then
the bulk-directory rows, each group in UUIDv7 (import) order. That needs a
two-field keyset cursor, following the `directory/covers.py` precedent. An
id-only cursor would page in seed-file order, which is arbitrary, and bury the
checked entries behind hundreds of unchecked ones.
"""

from __future__ import annotations

import base64
import re
import uuid
from typing import cast

from sqlalchemy import ColumnElement, Select, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload

from shared.geo.models import District, State
from shared.pagination import DEFAULT_PAGE_SIZE, InvalidCursorError, Page, paginate

from .models import Guide, Institution, InstitutionProgramme, Programme, StudentResource
from .schemas import InstitutionPage, StateFacet, to_card

# verified sorts first; reused in the cursor predicate, so it is defined once
# rather than restated at each use site.
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
TRUSTS = ("verified", "listed")
RESOURCE_KINDS = ("scholarship", "exam")
RESOURCE_CATEGORIES = ("entrance", "recruitment", "language_test")
RESOURCE_SCOPES = ("india", "international")
GUIDE_KINDS = ("counselling", "foreign_study", "general")

# Mirrors state_slug() in SQL so the comparison happens in the database rather
# than by loading all 36 states per request. The two must agree; a contract
# test walks every real state name and asserts they do.
_SQL_SLUG = "[^a-zA-Z0-9]+"


class UnknownFilter(ValueError):
    """A filter value outside its enum. 422, not a silent empty page."""


def state_slug(name: str) -> str:
    """The ONE place a state name becomes a URL segment.

    `/education/states` publishes what this produces and the `?state=` filter
    resolves through it, so the vocabulary cannot drift between a link and the
    page it points at. Deliberately NOT `citySlug()` from packages/ui — that
    one normalizes NFKD and strips diacritics, and two implementations of a
    slug on opposite sides of an HTTP boundary is the whole problem.
    """
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def _sql_slug(column: InstrumentedAttribute[str]) -> ColumnElement[str]:
    """state_slug(), in SQL.

    Typed rather than left as `object` so the `== state_slug(...)` comparison
    below produces a SQL predicate instead of a Python bool that SQLAlchemy
    would silently accept and then never filter on.
    """
    return cast(
        "ColumnElement[str]",
        func.trim(func.lower(func.regexp_replace(column, _SQL_SLUG, "-", "g")), "-"),
    )


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
    """Active rows only.

    Structural, like content's `_published()`: every list query starts here, so
    a handler cannot serve a closed college by forgetting a filter. Detail
    lookups deliberately do NOT use this -- a closed or merged institution must
    stay reachable by slug for the 301 and the closed banner of spec section 7.
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
    query = _listable().options(selectinload(Institution.state), selectinload(Institution.district))

    if kind is not None:
        if kind not in KINDS:
            raise UnknownFilter(kind)
        query = query.where(Institution.kind == kind)
    if trust is not None:
        if trust not in TRUSTS:
            raise UnknownFilter(trust)
        query = query.where(Institution.trust == trust)
    if is_government is not None:
        query = query.where(Institution.is_government.is_(is_government))
    if country is not None:
        query = query.where(Institution.country_code == country.upper())
    if state is not None:
        # Resolved through the SQL mirror of state_slug so the filter speaks
        # the same vocabulary /education/states publishes.
        query = query.join(State, Institution.state_id == State.id).where(
            _sql_slug(State.name) == state_slug(state)
        )
    if district is not None:
        # Joins District.lgd_code, NOT District.id: district_id holds the LGD
        # code because geo.districts is Tamil Nadu only until D65 and an FK
        # would reject a valid Punjab college (models.py). Consequence: a
        # district filter outside TN correctly returns nothing, because we do
        # not know those district ids yet.
        query = query.join(District, Institution.district_id == District.lgd_code).where(
            _sql_slug(District.name) == state_slug(district)
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
        # ILIKE, not Meili: the corpus is ~772 rows and routing this through
        # the search stack would give a dead Meili a way to break a college
        # page. Escape the wildcards -- a user typing "100%" must search for
        # that string, not match every row.
        needle = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(
            or_(Institution.name_en.ilike(needle), Institution.short_name.ilike(needle))
        )

    if cursor is not None:
        cursor_rank, cursor_id = decode_institution_cursor(cursor)
        # The rank tie-break MUST be part of the predicate. Without the second
        # clause every row sharing the boundary rank is skipped.
        # and_() rather than `&`: with `&`, mypy types the left operand as a
        # plain bool and the whole predicate silently degrades to a Python
        # comparison that SQLAlchemy would accept and never filter on.
        # noqa SIM300: _TRUST_RANK is an UPPERCASE name but a SQL expression,
        # not a literal. Ruff reads `_TRUST_RANK > cursor_rank` as a Yoda
        # condition and would flip it; keeping the SQL expression on the left
        # is what makes this read as the keyset predicate it is.
        query = query.where(
            or_(
                _TRUST_RANK > cursor_rank,  # noqa: SIM300
                and_(_TRUST_RANK == cursor_rank, Institution.id > cursor_id),  # noqa: SIM300
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
    """By slug, ANY status -- a closed or merged institution must resolve so
    the page can render its banner or issue its 301 (spec section 7)."""
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
    institution: Institution | None = await session.scalar(query)
    return institution


async def state_facets(session: AsyncSession) -> list[StateFacet]:
    """States with at least one active institution, and how many.

    The join is the point: 19 states have no agri institution at all, and
    generating an ISR page for each would publish 19 thin indexable pages with
    nothing on them.
    """
    query = (
        select(State.name, func.count(Institution.id))
        .join(Institution, Institution.state_id == State.id)
        .where(Institution.status == "active")
        .group_by(State.name)
        .order_by(State.name)
    )
    return [
        StateFacet(slug=state_slug(name), name=name, institution_count=count)
        for name, count in (await session.execute(query)).all()
    ]


# ── programmes ───────────────────────────────────────────────────────


async def list_programmes(session: AsyncSession) -> list[Programme]:
    """The whole catalog, uncursored: ~47 rows of registry-as-data, and a
    cursor here would be ceremony."""
    return list(await session.scalars(select(Programme).order_by(Programme.slug)))


# ── student resources (scholarships and exams) ───────────────────────


def _live_resources() -> Select[tuple[StudentResource]]:
    """Active rows only. Structural, like `_listable()`: an expired
    scholarship listed as live wastes a student's application."""
    return select(StudentResource).where(StudentResource.status == "active")


async def list_resources(
    session: AsyncSession,
    *,
    kind: str | None = None,
    category: str | None = None,
    scope: str | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> Page[StudentResource]:
    query = _live_resources()
    if kind is not None:
        if kind not in RESOURCE_KINDS:
            raise UnknownFilter(kind)
        query = query.where(StudentResource.kind == kind)
    if category is not None:
        if category not in RESOURCE_CATEGORIES:
            raise UnknownFilter(category)
        query = query.where(StudentResource.category == category)
    if scope is not None:
        if scope not in RESOURCE_SCOPES:
            raise UnknownFilter(scope)
        query = query.where(StudentResource.scope == scope)
    return await paginate(session, query, cursor=cursor, limit=limit)


async def get_resource(session: AsyncSession, slug: str) -> StudentResource | None:
    """Starts from the gated select: an archived resource is indistinguishable
    from one that never existed."""
    resource: StudentResource | None = await session.scalar(
        _live_resources().where(StudentResource.slug == slug)
    )
    return resource


# ── guides ───────────────────────────────────────────────────────────


def _published_guides() -> Select[tuple[Guide]]:
    """Published only. Structural, so no route can serve a draft by forgetting
    a filter."""
    return select(Guide).where(Guide.status == "published")


async def list_guides(
    session: AsyncSession,
    *,
    kind: str | None = None,
    country: str | None = None,
    state: str | None = None,
) -> list[tuple[Guide, str | None]]:
    """Uncursored: 13 rows of bounded registry. Returns each guide with its
    state NAME, since the wire shape carries a name rather than an id."""
    query = _published_guides().order_by(Guide.slug)
    if kind is not None:
        if kind not in GUIDE_KINDS:
            raise UnknownFilter(kind)
        query = query.where(Guide.kind == kind)
    if country is not None:
        query = query.where(Guide.country_code == country.upper())
    if state is not None:
        query = query.join(State, Guide.state_id == State.id).where(
            _sql_slug(State.name) == state_slug(state)
        )
    rows = (
        await session.execute(
            query.add_columns(State.name).outerjoin(State, Guide.state_id == State.id)
            if state is None
            else query.add_columns(State.name)
        )
    ).all()
    return [(guide, state_name) for guide, state_name in rows]


async def get_guide(session: AsyncSession, slug: str) -> tuple[Guide, str | None] | None:
    """A draft and a nonexistent slug answer identically: an unreviewed guide
    must not be discoverable by guessing."""
    row = (
        await session.execute(
            _published_guides()
            .where(Guide.slug == slug)
            .add_columns(State.name)
            .outerjoin(State, Guide.state_id == State.id)
        )
    ).first()
    return (row[0], row[1]) if row is not None else None
