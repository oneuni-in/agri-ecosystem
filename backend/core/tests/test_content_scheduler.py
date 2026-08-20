"""A-U4b O3 — the content scheduler's day-covered decision.

Only the PURE decision is tested here: given the content.ingest_runs
ledger, should the boot catch-up stand down? The loop around it (sleep
until the IST hour, retry on failure) is the same shape the mandi
scheduler runs in production and is deliberately not simulated.

The semantic under test is the one that differs from mandi: an `empty`
outcome means "feed reached, nothing new" — a COMPLETED pull — so ok OR
empty covers the day, failures never do, and an unreadable ledger
decides towards pulling (duplicate pulls are free; items dedupe on the
canonical URL).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.content.models import (
    OUTCOME_EMPTY,
    OUTCOME_FETCH_FAILED,
    OUTCOME_OK,
    OUTCOME_WRITE_FAILED,
    IngestRun,
)
from scripts.content_scheduler import IST, _day_covered_safely, day_covered, now_ist

pytestmark = pytest.mark.anyio


async def _run(session: AsyncSession, outcome: str, started_at: datetime | None = None) -> None:
    session.add(
        IngestRun(
            source_slug="the-hindu",
            started_at=started_at or datetime.now(UTC),
            outcome=outcome,
        )
    )
    await session.flush()


async def test_ok_run_today_covers_the_day(db_session: AsyncSession) -> None:
    await _run(db_session, OUTCOME_OK)
    assert await day_covered(db_session, now_ist().date()) is True


async def test_empty_run_today_covers_the_day(db_session: AsyncSession) -> None:
    """The divergence from mandi: an empty content pull is a COMPLETED
    pull ("feed reached, nothing new"), not "too early in the day"."""
    await _run(db_session, OUTCOME_EMPTY)
    assert await day_covered(db_session, now_ist().date()) is True


async def test_only_failed_runs_do_not_cover_the_day(db_session: AsyncSession) -> None:
    """A failure is a reason to try again, never to stand down."""
    await _run(db_session, OUTCOME_FETCH_FAILED)
    await _run(db_session, OUTCOME_WRITE_FAILED)
    assert await day_covered(db_session, now_ist().date()) is False


async def test_no_runs_do_not_cover_the_day(db_session: AsyncSession) -> None:
    assert await day_covered(db_session, now_ist().date()) is False


async def test_yesterdays_ok_run_does_not_cover_today(db_session: AsyncSession) -> None:
    """The boundary is the IST midnight, not a 24h window."""
    today_start_ist = now_ist().replace(hour=0, minute=0, second=0, microsecond=0)
    just_before_midnight = (today_start_ist - timedelta(minutes=5)).astimezone(UTC)
    await _run(db_session, OUTCOME_OK, started_at=just_before_midnight)
    assert await day_covered(db_session, now_ist().date()) is False
    # ... and the same instant IS covered when asked about yesterday.
    assert await day_covered(db_session, just_before_midnight.astimezone(IST).date()) is True


async def test_unreadable_ledger_means_pull_anyway(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the ledger cannot be read, the answer is "not covered": a
    duplicate pull is free, a skipped day is not."""

    def boom() -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr("scripts.content_scheduler.get_sessionmaker", boom)
    assert await _day_covered_safely(now_ist().date()) is False
