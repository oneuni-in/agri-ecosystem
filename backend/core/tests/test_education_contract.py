"""Properties of the education API that must survive refactoring.

These do not test a function; they test a promise. Each one is a rule that is
cheap to break by accident, expensive to notice, and harmful in production --
a fee on an unchecked college, a state slug that 404s against its own link, a
LIKE wildcard that leaks the whole corpus.

Several run against the REAL committed corpus rather than a fixture pair. That
is deliberate: the risks here are about the odd row nobody thought to write a
case for.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.education.models import Institution
from modules.education.schemas import can_show_admission_data, to_detail
from modules.education.seed_import import import_bundle
from modules.education.service import (
    get_institution,
    list_institutions,
    state_facets,
    state_slug,
)
from shared.geo.loader import load_geo
from shared.geo.models import State

SEED = Path(__file__).resolve().parents[1] / "data" / "seeds" / "education"
GEO = Path(__file__).resolve().parents[1] / "data" / "geo"
TODAY = date(2026, 8, 17)


@pytest.fixture
async def geo_only(owner_session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """The real 36-state snapshot, without the education corpus."""
    await load_geo(owner_session, GEO)
    await owner_session.flush()
    yield owner_session


@pytest.fixture
async def corpus(geo_only: AsyncSession) -> AsyncIterator[AsyncSession]:
    """The real committed bundle: 772 institutions and everything else."""
    await import_bundle(geo_only, SEED, GEO, today=TODAY)
    yield geo_only


async def test_the_sql_and_python_state_slugs_agree_on_every_real_state(
    geo_only: AsyncSession,
) -> None:
    """The `?state=` filter slugifies in SQL; /education/states slugifies in
    Python. Those two must not drift, and this is where the drift would come
    back one layer down -- silently, on the one state name with a period or an
    ampersand in it.

    Walks the real geo dataset, not a sample: the whole risk is the odd name
    nobody thought to write a case for.
    """
    rows = (
        await geo_only.execute(
            select(
                State.name,
                func.trim(
                    func.lower(func.regexp_replace(State.name, "[^a-zA-Z0-9]+", "-", "g")), "-"
                ),
            )
        )
    ).all()
    assert rows, "geo.states is empty -- load the geo seed before trusting this test"
    assert len(rows) >= 36

    mismatches = [(name, sql) for name, sql in rows if sql != state_slug(name)]
    assert not mismatches, f"SQL and Python slugs disagree: {mismatches}"


async def test_every_state_facet_slug_resolves_to_a_nonempty_filter(
    corpus: AsyncSession,
) -> None:
    """Every slug the API publishes must work as a filter against the API that
    published it. This is the end-to-end version of the test above: it would
    catch a drift the string comparison missed."""
    facets = await state_facets(corpus)
    assert facets, "no state has an institution -- the corpus did not import"

    for facet in facets:
        page = await list_institutions(corpus, state=facet.slug, limit=1)
        assert page.items, f"{facet.slug!r} was published with 0 results"


async def test_state_facets_exclude_states_with_no_colleges(
    corpus: AsyncSession,
) -> None:
    """19 states have no agri institution at all. Publishing them would give
    the frontend 19 thin, empty, indexable pages to generate."""
    facets = await state_facets(corpus)
    total_states = await corpus.scalar(select(func.count()).select_from(State))

    assert all(f.institution_count > 0 for f in facets)
    assert total_states is not None and len(facets) < total_states, (
        "every state has colleges, which contradicts the corpus audit"
    )


async def test_no_unverified_institution_anywhere_in_the_corpus_emits_a_fee(
    corpus: AsyncSession,
) -> None:
    """Walks every institution the list serves and fetches each detail.

    Slow and deliberately exhaustive: can_show_admission_data is one predicate
    today, and the day someone adds a second serialization path -- a summary
    endpoint, a sitemap feed, an export -- this is the test that notices the
    fee that came with it.
    """
    cursor: str | None = None
    checked = 0
    while True:
        page = await list_institutions(corpus, cursor=cursor, limit=100)
        for card in page.items:
            if card.can_show_admission_data:
                continue
            row = await get_institution(corpus, card.slug)
            assert row is not None
            for offering in to_detail(row).programmes:
                assert offering.intake_seats is None, card.slug
                assert offering.annual_fees_inr is None, card.slug
                assert offering.admission_route is None, card.slug
            checked += 1
        cursor = page.next_cursor
        if cursor is None:
            break

    assert checked > 0, "the corpus has no unverified rows, so this proved nothing"


async def test_the_predicate_and_the_search_snapshot_agree_on_visibility(
    corpus: AsyncSession,
) -> None:
    """Two independent gates decide the same thing: can_show_admission_data
    guards what a page may render, institution_snapshot guards what hub search
    may index. They read the same two columns and must never disagree -- a
    college findable in search but showing nothing, or the reverse, is a
    contradiction a user would see."""
    from modules.education.search_sync import institution_snapshot

    rows = list(await corpus.scalars(select(Institution).limit(300)))
    assert rows

    for row in rows:
        assert can_show_admission_data(row) == (institution_snapshot(row, None) is not None), (
            row.slug
        )


async def test_the_ilike_search_treats_wildcards_as_text(corpus: AsyncSession) -> None:
    """A user typing '%' must search for that character, not match every row.
    Unescaped, q=% returns all 772."""
    assert (await list_institutions(corpus, q="%")).items == []
    assert (await list_institutions(corpus, q="_")).items == []
    assert (await list_institutions(corpus, q="\\")).items == []
    # ...and a real query still works, or the escaping broke search instead.
    assert (await list_institutions(corpus, q="Agricultural")).items


async def test_the_district_filter_is_tamil_nadu_only_and_says_so_by_returning_nothing(
    corpus: AsyncSession,
) -> None:
    """geo.districts holds 38 rows, all Tamil Nadu, until D65. A district
    filter elsewhere returns nothing because we do not know those district
    ids -- not because there are no colleges there. Plan 3 must not offer the
    control outside TN, and this test is where that fact is recorded."""
    assert (await list_institutions(corpus, district="coimbatore")).items
    assert (await list_institutions(corpus, district="ludhiana")).items == []

    # Punjab has colleges; only its DISTRICTS are unknown.
    assert (await list_institutions(corpus, state="punjab")).items


async def test_every_listed_row_is_absent_from_search_and_every_verified_one_is_not(
    corpus: AsyncSession,
) -> None:
    """The corpus-wide version of the trust rule: no bulk-directory row may
    become a searchable document."""
    from modules.education.search_sync import institution_snapshot

    listed = list(
        await corpus.scalars(select(Institution).where(Institution.trust == "listed").limit(200))
    )
    assert listed, "no listed rows -- this proved nothing"
    assert all(institution_snapshot(row, None) is None for row in listed)

    verified_active = list(
        await corpus.scalars(
            select(Institution)
            .where(Institution.trust == "verified", Institution.status == "active")
            .limit(200)
        )
    )
    assert verified_active
    assert all(institution_snapshot(row, None) is not None for row in verified_active)
