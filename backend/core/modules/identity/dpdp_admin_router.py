"""The DPDP data-requests queue for staff (ID-U1 W4).

The A6 surface the erasure flow reports into: what has been asked for, what
is holding it, and the two decisions a human can take.

Deliberately narrow. Staff can SEE every request and can RELEASE a hold or
RUN a due erasure now - and that is all. There is no "delete this person"
button that skips the grace window, because a queue that can start an
irreversible action a user never asked for is a bigger risk than the one it
manages. Every erasure here began with the user's own request.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.dpdp_models import ErasureRequest
from modules.identity.dpdp_service import cancel_erasure, erase_user
from modules.identity.models import User
from shared.audit import audit
from shared.authz import require_permission
from shared.db import get_session
from shared.security import SecureRouter

dpdp_admin_router = SecureRouter(prefix="/admin/data-requests", tags=["admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class DataRequestOut(BaseModel):
    id: str
    # the PUBLIC identity, never the internal uuid (schemas.py guard rule)
    agri_id: str
    status: str
    requested_at: datetime
    execute_after: datetime
    # staff-facing only: these name another module's business state and are
    # never returned on the user-facing route
    hold_reasons: list[str]
    executed_at: datetime | None


class DataRequestsOut(BaseModel):
    items: list[DataRequestOut]


def _out(row: ErasureRequest, agri_id: str) -> DataRequestOut:
    return DataRequestOut(
        id=str(row.id),
        agri_id=agri_id,
        status=row.status,
        requested_at=row.created_at,
        execute_after=row.execute_after,
        hold_reasons=row.hold_reasons.split(",") if row.hold_reasons else [],
        executed_at=row.executed_at,
    )


@dpdp_admin_router.get("", dependencies=[require_permission("dpdp.read")])
async def list_data_requests(
    session: SessionDep,
    status: Annotated[Literal["pending", "held", "executed", "cancelled"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> DataRequestsOut:
    """Held first, then newest: a held request is the only kind waiting on a
    human, so it is the only kind that should be at the top."""
    query = (
        select(ErasureRequest, User.agri_id)
        .join(User, User.id == ErasureRequest.user_id)
        .order_by(
            (ErasureRequest.status != "held"),  # False (held) sorts first
            ErasureRequest.created_at.desc(),
        )
        .limit(limit)
    )
    if status is not None:
        query = query.where(ErasureRequest.status == status)
    rows = (await session.execute(query)).all()
    return DataRequestsOut(items=[_out(row, agri_id) for row, agri_id in rows])


async def _load(session: AsyncSession, request_id: str) -> ErasureRequest:
    try:
        row_id = uuid.UUID(request_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="unknown_request") from exc
    row = await session.get(ErasureRequest, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown_request")
    return row


@dpdp_admin_router.post("/{request_id}/release", dependencies=[require_permission("dpdp.decide")])
async def release_hold(
    request_id: str, principal_request: Request, session: SessionDep
) -> DataRequestOut:
    """Clear a hold and let the erasure proceed on the next run.

    This does NOT erase anything now. It removes the reason the system was
    pausing, and the job does the rest on its own schedule - so a release
    made in error is still recoverable by the user withdrawing, right up
    until the job runs.
    """
    row = await _load(session, request_id)
    if row.status != "held":
        raise HTTPException(status_code=409, detail="not_held")
    row.status = "pending"
    row.hold_reasons = None
    actor = getattr(principal_request.state, "principal", None)
    await audit(
        session,
        action="dpdp.hold_released",
        actor_user_id=getattr(actor, "user_id", None),
        target_type="erasure_request",
        target_id=str(row.id),
        ip=principal_request.client.host if principal_request.client else None,
    )
    await session.commit()
    user = await session.get(User, row.user_id)
    return _out(row, user.agri_id if user else "")


@dpdp_admin_router.post("/{request_id}/execute", dependencies=[require_permission("dpdp.decide")])
async def execute_now(
    request_id: str, principal_request: Request, session: SessionDep
) -> DataRequestOut:
    """Run a DUE erasure immediately instead of waiting for the next job tick.

    The grace window is still enforced: a request whose `execute_after` has
    not passed is refused. Staff can skip the *scheduler*, never the promise
    made to the user about how long they have to change their mind.
    """
    row = await _load(session, request_id)
    if row.status not in ("pending", "held"):
        raise HTTPException(status_code=409, detail="not_open")
    if row.execute_after > datetime.now(UTC):
        raise HTTPException(status_code=409, detail="grace_not_elapsed")
    counts = await erase_user(session, row.user_id)
    row.status = "executed"
    row.hold_reasons = None
    row.executed_at = datetime.now(UTC)
    actor = getattr(principal_request.state, "principal", None)
    await audit(
        session,
        action="dpdp.erasure_executed",
        actor_user_id=getattr(actor, "user_id", None),
        target_type="erasure_request",
        target_id=str(row.id),
        metadata={"rows": counts},
        ip=principal_request.client.host if principal_request.client else None,
    )
    await session.commit()
    return _out(row, "")


@dpdp_admin_router.post("/{request_id}/cancel", dependencies=[require_permission("dpdp.decide")])
async def cancel_on_behalf(
    request_id: str, principal_request: Request, session: SessionDep
) -> DataRequestOut:
    """Withdraw a request on the user's behalf - for the support call that
    starts "I didn't mean to press that"."""
    row = await _load(session, request_id)
    actor = getattr(principal_request.state, "principal", None)
    try:
        row = await cancel_erasure(session, row.user_id, closed_by=getattr(actor, "user_id", None))
    except Exception as exc:  # service raises when nothing is open
        raise HTTPException(status_code=409, detail="not_open") from exc
    await audit(
        session,
        action="dpdp.erasure_withdrawn_by_staff",
        actor_user_id=getattr(actor, "user_id", None),
        target_type="erasure_request",
        target_id=str(row.id),
        ip=principal_request.client.host if principal_request.client else None,
    )
    await session.commit()
    user = await session.get(User, row.user_id)
    return _out(row, user.agri_id if user else "")
