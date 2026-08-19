"""A-U4 follow-up — AG-A40's second half: one wallet across the family.

The row asks that a balance "matches milk.in". Until now that was answered
with an argument rather than a test: there is one `coins.balances` row per
user, one engine, one schema, and no per-vertical balance column, so the two
sites cannot disagree because there is only ever one figure to read.

That argument is correct, and it is exactly the kind of correct that stops
being true silently. Nothing prevented a future migration from adding a
`site` column to `balances` for what would look like a good local reason —
per-site reporting, say — and splitting the wallet in two without a single
test going red. "True by construction" is only worth as much as the
construction, so this file asserts the construction itself.

Two levels, deliberately:

  1. SCHEMA. The wallet is keyed by user and nothing else. A site/vertical
     column appearing on the ledger or the balance is the specific way this
     invariant would break, so it fails here rather than in production.
  2. BEHAVIOUR. Earnings that originate on different sites land in the same
     single balance row.

Neither needs the web apps running: the claim is about the engine, and the
engine is shared. Driving two browsers would test the two front-ends' ability
to read a number, which is not what the row is about.
"""

import uuid
from typing import cast

import pytest
from sqlalchemy import Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins import service
from modules.coins.models import Balance, LedgerEntry

# Words that would indicate the wallet had been scoped to one site. Not an
# exhaustive list of bad names — it is the set of names someone would
# plausibly reach for while splitting a shared wallet.
SITE_SCOPED_HINTS = ("site", "vertical", "platform", "tenant", "brand", "app_")


def _site_scoped_columns(table: Table) -> list[str]:
    return [
        column.name
        for column in table.columns
        if any(hint in column.name.lower() for hint in SITE_SCOPED_HINTS)
    ]


def test_balance_is_keyed_by_user_and_nothing_else() -> None:
    """The whole cross-platform guarantee, expressed as a primary key."""
    # cast: SQLAlchemy declares __table__ as FromClause; these are real Tables.
    balances = cast(Table, Balance.__table__)
    pk = [c.name for c in balances.primary_key.columns]
    assert pk == ["user_id"], (
        f"coins.balances is keyed by {pk}. A composite key is how one wallet "
        "becomes two — a user would hold a different balance per site and "
        "AG-A40's 'matches milk.in' would quietly stop being true."
    )


def test_no_site_column_on_the_wallet_or_the_ledger() -> None:
    """The migration that would split the wallet, caught at the schema."""
    tables = (cast(Table, Balance.__table__), cast(Table, LedgerEntry.__table__))
    for table in tables:
        offenders = _site_scoped_columns(table)
        assert offenders == [], (
            f"coins.{table.name} grew site-scoped column(s) {offenders}. "
            "The family shares one wallet by construction; scoping the "
            "ledger or the balance to a site breaks that silently, because "
            "every existing test would still pass."
        )


@pytest.mark.asyncio
async def test_earnings_from_both_sites_land_in_one_balance(db_session: AsyncSession) -> None:
    """A milk earning and an agri earning, one user, one balance.

    `review_approved` and `business_claim` are not milk-specific or
    agri-specific codes — that is the point. The engine is never told which
    site an earning came from, so it has nothing to split on.
    """
    uid = uuid.uuid4()

    # Earned on milk.in: a dairy review approved.
    await service.record_entry(
        db_session,
        user_id=uid,
        delta=5,
        reason_code="review_approved",
        ref_type="review",
        ref_id=f"milk-review-{uid}",
        idempotency_key=f"milk:review:{uid}",
    )
    # Earned on agri.in: a business claim approved.
    await service.record_entry(
        db_session,
        user_id=uid,
        delta=25,
        reason_code="business_claim",
        ref_type="business",
        ref_id=f"agri-business-{uid}",
        idempotency_key=f"agri:claim:{uid}",
    )
    await db_session.flush()

    balance_rows = await db_session.scalar(
        select(func.count()).select_from(Balance).where(Balance.user_id == uid)
    )
    balance = await db_session.scalar(select(Balance.balance).where(Balance.user_id == uid))
    ledger_rows = await db_session.scalar(
        select(func.count()).select_from(LedgerEntry).where(LedgerEntry.user_id == uid)
    )

    assert balance_rows == 1, (
        f"{balance_rows} balance rows for one user — the wallet has been split per site"
    )
    assert ledger_rows == 2, "both earnings must be on the one shared ledger"
    assert balance == 30, (
        f"balance {balance} != 5 + 25. Whichever site the visitor opens, this "
        "is the single number both of them read."
    )
