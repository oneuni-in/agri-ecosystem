"""Business reports service (M1.5.A): login-gated user reports feeding the
unified moderation queue. The router maps errors to HTTP statuses; the
moderation source (moderation_sources.ReportSource) wraps moderate().

Anti-brigading is layered: a fail-closed per-user daily cap (reveal.py
precedent) plus a one-open-report-per-(business, reporter) partial unique
index. Enforcement on the business itself is ALWAYS a separate human
decision - nothing here touches Business.status."""

import uuid
from datetime import datetime, timedelta

from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory.models import Report
from settings import get_settings
from shared.cache import get_redis
from shared.pagination import DEFAULT_PAGE_SIZE, Page, paginate

_DAY_SECONDS = 86400


class ReportsError(Exception):
    pass


class ReportExistsError(ReportsError):
    pass


class ReportCapExceededError(ReportsError):
    pass


class ReportsUnavailableError(ReportsError):
    pass


class ReportNotFoundError(ReportsError):
    pass


class ReportDecisionConflictError(ReportsError):
    pass


async def claim_report_slot(user_id: uuid.UUID, *, now: datetime) -> None:
    """Fail-closed daily report cap (reveal.py precedent): Redis down means
    503, never an uncapped report; increment-before-act costs a slot on crash."""
    cap = get_settings().report_daily_cap
    key = f"report:{user_id}:{now.strftime('%Y%m%d')}"
    try:
        redis = get_redis()
        count = int(await redis.incr(key))
        if count == 1:
            await redis.expire(key, _DAY_SECONDS)
    except RedisError as exc:
        raise ReportsUnavailableError() from exc
    if count > cap:
        raise ReportCapExceededError()


async def create_report(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    reporter_user_id: uuid.UUID,
    reason: str,
    detail: str | None,
) -> Report:
    report = Report(
        business_id=business_id,
        reporter_user_id=reporter_user_id,
        reason=reason,
        detail=detail,
    )
    sp = await session.begin_nested()
    try:
        session.add(report)
        await session.flush()
    except IntegrityError as exc:
        await sp.rollback()
        raise ReportExistsError(str(business_id)) from exc
    await sp.commit()
    return report


async def list_for_moderation(
    session: AsyncSession,
    *,
    status: str = "pending",
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> Page[Report]:
    query = select(Report).where(Report.moderation_status == status)
    return await paginate(session, query, cursor=cursor, limit=limit)


async def reporter_report_count(
    session: AsyncSession, reporter_user_id: uuid.UUID, *, now: datetime, days: int = 30
) -> int:
    """Admin-side brigading signal: how many reports this user filed recently."""
    return (
        await session.scalar(
            select(func.count())
            .select_from(Report)
            .where(
                Report.reporter_user_id == reporter_user_id,
                Report.created_at >= now - timedelta(days=days),
            )
        )
    ) or 0


async def moderate(session: AsyncSession, *, report_id: uuid.UUID, approve: bool) -> Report:
    """Decide a pending report. approve=True means 'actioned' (valid report);
    False means 'dismissed'. Row-locked; deciding twice conflicts."""
    report = await session.scalar(select(Report).where(Report.id == report_id).with_for_update())
    if report is None:
        raise ReportNotFoundError(str(report_id))
    if report.moderation_status != "pending":
        raise ReportDecisionConflictError("already_decided")
    report.moderation_status = "approved" if approve else "rejected"
    await session.flush()
    return report
