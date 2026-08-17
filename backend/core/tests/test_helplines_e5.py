"""A-U3 W2 — helplines as an E5 dataset (the A-U1 static-file debt paid).

The static `apps/web-agri/data/helplines.ts` is DELETED in the same
commit as this suite. These tests exist to make sure nothing about the
band regressed in the move, and to pin the two rules the static file
could not express: per-number provenance, and state scoping.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.market_data.models import Helpline
from modules.market_data.service import get_helplines

from .d26_helpers import api  # noqa: F401 — the shared client fixture

pytestmark = pytest.mark.anyio


async def test_migration_seeds_the_four_a_u1_numbers(db_session: AsyncSession) -> None:
    """The exact four the A-U1 band rendered, carried over unchanged."""
    rows = (await db_session.scalars(select(Helpline).order_by(Helpline.sort_order))).all()
    assert [r.slug for r in rows] == ["kcc", "tn-agri", "animal-husbandry", "pm-kisan"]
    assert [r.number for r in rows] == [
        "1800-180-1551",
        "1800-425-1556",
        "1962",
        "155261",
    ]


async def test_every_number_carries_its_own_source_and_date(db_session: AsyncSession) -> None:
    """market_data/CLAUDE.md: never serve a dataset without source + as-of.
    Here that is PER NUMBER, not per table — the UI renders it, so a
    number nobody re-checked says so on screen."""
    for row in (await db_session.scalars(select(Helpline))).all():
        assert row.source and row.source_url and row.verified_on
        assert row.source_url.startswith("https://")
        # Official domains only, the AG-A11 rule extended to helplines.
        assert row.source.endswith(".gov.in")


async def test_only_the_recheckable_number_was_restamped(db_session: AsyncSession) -> None:
    """0039's rule, applied again: moving data into a table is NOT
    verification. Only the KCC number could be confirmed against a
    primary source on 2026-08-17, so only it carries that date; the other
    three keep their original A-U1 human check."""
    rows = {r.slug: r for r in (await db_session.scalars(select(Helpline))).all()}
    assert rows["kcc"].verified_on == date(2026, 8, 17)
    assert rows["kcc"].source == "agriwelfare.gov.in"
    for slug in ("tn-agri", "animal-husbandry", "pm-kisan"):
        assert rows[slug].verified_on == date(2026, 8, 14), (
            f"{slug} was restamped without anyone re-verifying it"
        )


async def test_a_state_helpline_is_not_offered_outside_its_state(
    db_session: AsyncSession,
) -> None:
    """Showing a Tamil Nadu number to someone in Bihar is not a bonus
    row — it is a number that will not help them, printed with the same
    authority as one that would."""
    national = await get_helplines(db_session)
    assert "tn-agri" not in {h.slug for h in national}

    in_tn = await get_helplines(db_session, "Tamil Nadu")
    assert "tn-agri" in {h.slug for h in in_tn}
    assert len(in_tn) == len(national) + 1

    elsewhere = await get_helplines(db_session, "Bihar")
    assert {h.slug for h in elsewhere} == {h.slug for h in national}


async def test_route_serves_the_dataset_with_stamps(api) -> None:  # noqa: F811
    client, _ = api
    body = (await client.get("/market/helplines?state=Tamil Nadu")).json()
    assert len(body) == 4
    kcc = next(h for h in body if h["slug"] == "kcc")
    # Name is DATA now, in three languages — not an i18n key.
    assert set(kcc["name"]) == {"en", "ta", "hi"}
    assert kcc["dial"] == "18001801551"
    assert kcc["verified_on"] == "2026-08-17"
    assert kcc["source"] == "agriwelfare.gov.in"


async def test_static_helplines_file_is_gone() -> None:
    """The A-U3 prompt is explicit: after migration the static file is
    deleted, NOT left as a dead fallback. Two copies of a phone number is
    two things to keep true, and the stale one always wins eventually."""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[3]
    assert not (repo / "apps" / "web-agri" / "data" / "helplines.ts").exists()
