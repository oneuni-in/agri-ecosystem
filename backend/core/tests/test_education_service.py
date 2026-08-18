"""education read service: trust and status decide what may be serialized.

The suppression tests deliberately insert rows the seed contract forbids
(rule 10: no seats/fees/admission_route on a `listed` row). That is the point
-- if the only thing stopping a fee reaching a student is that the CSV happened
not to contain one, then a bad import, a hand-fixed row or a future admin write
becomes a correctness bug on a public page. The gate has to hold against a
database that is already wrong.

Writes take `owner_session`, reads take it too here because the rows have to
exist first: education grants app_rt SELECT only (0049).
"""

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.education.models import Institution, InstitutionProgramme, Programme
from modules.education.schemas import to_card, to_detail
from modules.education.service import (
    UnknownFilter,
    get_institution,
    list_institutions,
    state_slug,
)


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
        slug=f"bsc-ag-{inst.slug}",
        name_en="B.Sc. Agriculture",
        level="ug",
        discipline="agriculture",
        duration_months=48,
    )
    session.add(programme)
    await session.flush()
    session.add(
        InstitutionProgramme(
            institution_id=inst.id,
            programme_id=programme.id,
            intake_seats=seats,
            annual_fees_inr=fees,
            admission_route="TNAU counselling",
            source_url="https://example.ac.in/fees",
            last_verified_at=date(2026, 8, 10),
        )
    )
    await session.flush()


async def _detail(session: AsyncSession, slug: str) -> object:
    row = await get_institution(session, slug)
    assert row is not None
    return to_detail(row)


async def test_a_listed_row_cannot_emit_seats_or_fees(owner_session: AsyncSession) -> None:
    """The row is poisoned on purpose: seats and fees present, trust=listed."""
    inst = await _inst(owner_session, "poisoned-college", trust="listed")
    await _offering(owner_session, inst, seats=120, fees=45000)

    detail = await _detail(owner_session, "poisoned-college")

    assert detail.trust == "listed"  # type: ignore[attr-defined]
    assert len(detail.programmes) == 1, "the offering itself is still listed"  # type: ignore[attr-defined]
    offering = detail.programmes[0]  # type: ignore[attr-defined]
    assert offering.intake_seats is None
    assert offering.annual_fees_inr is None
    assert offering.admission_route is None
    # ...but the programme is still named, because "this college runs B.Sc.
    # Agriculture" is true and useful.
    assert offering.name["en"] == "B.Sc. Agriculture"


async def test_a_closed_verified_row_cannot_emit_admission_data(
    owner_session: AsyncSession,
) -> None:
    """Spec section 7: a dead page still saying 'apply here' is the harmful case."""
    inst = await _inst(owner_session, "shut-college", trust="verified", status="closed")
    await _offering(owner_session, inst, seats=60, fees=30000)

    detail = await _detail(owner_session, "shut-college")

    assert detail.status == "closed"  # type: ignore[attr-defined]
    offering = detail.programmes[0]  # type: ignore[attr-defined]
    assert offering.intake_seats is None
    assert offering.annual_fees_inr is None


async def test_a_verified_active_row_emits_everything(owner_session: AsyncSession) -> None:
    """The negative tests above are only meaningful if the positive one passes."""
    inst = await _inst(owner_session, "good-college")
    await _offering(owner_session, inst, seats=80, fees=25000)

    detail = await _detail(owner_session, "good-college")

    offering = detail.programmes[0]  # type: ignore[attr-defined]
    assert offering.intake_seats == 80
    assert offering.annual_fees_inr == 25000
    assert offering.admission_route == "TNAU counselling"


async def test_cards_suppress_on_the_same_predicate_as_details(
    owner_session: AsyncSession,
) -> None:
    """Cards and details must not disagree -- a card is where a seat count
    would be most tempting to show and least likely to be reviewed.

    Loaded through get_institution rather than handed the flushed object:
    Institution.state is lazy="raise", so to_card on a row nobody eager-loaded
    raises instead of firing a silent per-row query. That is deliberate -- on
    a page of 100 colleges the alternative is 100 extra round-trips nobody
    notices until production.
    """
    await _inst(owner_session, "card-college", trust="listed")
    loaded = await get_institution(owner_session, "card-college")
    assert loaded is not None

    card = to_card(loaded)
    assert card.trust == "listed"
    assert card.can_show_admission_data is False
    assert to_detail(loaded).can_show_admission_data == card.can_show_admission_data


async def test_to_card_refuses_a_row_nobody_eager_loaded(
    owner_session: AsyncSession,
) -> None:
    """The guard above, asserted directly. A forgotten selectinload must fail
    loudly rather than degrade into an N+1 that only shows up under load."""
    from sqlalchemy import select
    from sqlalchemy.exc import InvalidRequestError

    await _inst(owner_session, "unloaded-college")
    owner_session.expunge_all()
    bare = await owner_session.scalar(
        select(Institution).where(Institution.slug == "unloaded-college")
    )
    assert bare is not None

    with pytest.raises(InvalidRequestError, match="lazy='raise'"):
        to_card(bare)


async def test_merged_and_closed_rows_stay_out_of_listings(
    owner_session: AsyncSession,
) -> None:
    live = await _inst(owner_session, "live-college")
    await _inst(owner_session, "gone-college", status="closed")
    await _inst(owner_session, "renamed-college", status="merged", merged_into_id=live.id)

    page = await list_institutions(owner_session)
    slugs = {row.slug for row in page.items}

    assert "live-college" in slugs
    assert "gone-college" not in slugs
    assert "renamed-college" not in slugs
    # ...but both remain reachable by slug, which is what makes the 301 and
    # the closed banner of spec section 7 possible at all.
    assert await get_institution(owner_session, "gone-college") is not None
    assert await get_institution(owner_session, "renamed-college") is not None


async def test_a_merged_row_carries_the_pointer_the_page_redirects_with(
    owner_session: AsyncSession,
) -> None:
    live = await _inst(owner_session, "successor-college")
    await _inst(owner_session, "old-college", status="merged", merged_into_id=live.id)

    detail = await _detail(owner_session, "old-college")

    assert detail.status == "merged"  # type: ignore[attr-defined]
    assert detail.merged_into_slug == "successor-college"  # type: ignore[attr-defined]


async def test_verified_rows_sort_before_listed_ones(owner_session: AsyncSession) -> None:
    """A student scanning a state page should meet checked entries first."""
    await _inst(owner_session, "bulk-a", trust="listed")
    await _inst(owner_session, "bulk-b", trust="listed")
    await _inst(owner_session, "checked", trust="verified")

    page = await list_institutions(owner_session)

    assert page.items[0].slug == "checked"


async def test_the_cursor_walks_the_whole_set_exactly_once(
    owner_session: AsyncSession,
) -> None:
    """A compound cursor is where paging bugs live: the rank tie-break has to
    be part of the predicate or rows are dropped at the boundary."""
    for i in range(7):
        await _inst(owner_session, f"page-{i}", trust="verified" if i < 3 else "listed")

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):  # bounded: a non-terminating cursor must fail, not hang
        page = await list_institutions(owner_session, cursor=cursor, limit=2)
        seen.extend(row.slug for row in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert cursor is None, "paging did not terminate"
    assert len(seen) == len(set(seen)) == 7


async def test_an_unknown_filter_value_raises_rather_than_returning_nothing(
    owner_session: AsyncSession,
) -> None:
    """An empty page tells a caller their filter matched nothing. A wrong enum
    value is a different fact and deserves a different answer."""
    with pytest.raises(UnknownFilter):
        await list_institutions(owner_session, kind="hogwarts")
    with pytest.raises(UnknownFilter):
        await list_institutions(owner_session, trust="probably")


async def test_the_search_filter_treats_wildcards_as_text(
    owner_session: AsyncSession,
) -> None:
    """A user typing '%' must search for that character, not match every row.
    Unescaped, q=% returns the entire corpus."""
    await _inst(owner_session, "plain-college", name_en="Plain College")

    assert (await list_institutions(owner_session, q="%")).items == []
    assert (await list_institutions(owner_session, q="_")).items == []
    assert [r.slug for r in (await list_institutions(owner_session, q="Plain")).items] == [
        "plain-college"
    ]


def test_state_slug_is_stable_for_the_shapes_state_names_take() -> None:
    assert state_slug("Tamil Nadu") == "tamil-nadu"
    assert state_slug("Jammu & Kashmir") == "jammu-kashmir"
    assert state_slug("Dadra & Nagar Haveli and Daman & Diu") == (
        "dadra-nagar-haveli-and-daman-diu"
    )
    assert state_slug("  Kerala  ") == "kerala"
