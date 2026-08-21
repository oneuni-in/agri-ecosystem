"""The three DPDP rights, owner-scoped (ID-U1 W4, closes the D56 gate item).

Every route here is on SecureRouter, so it is private and rate-limited by
default, and every one acts on `principal.user_id` ONLY. There is no route
that takes a user id: the IDOR-proof design is that the parameter does not
exist, which is stronger than checking it.

Per module rules nothing here logs bodies or query strings.
"""

import json
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.dpdp_service import (
    ErasureError,
    build_export,
    cancel_erasure,
    open_request,
    request_erasure,
)
from modules.identity.models import User
from modules.identity.rbac import require_permission
from modules.identity.session_auth import PrincipalDep
from shared import dpdp
from shared.audit import audit
from shared.db import get_session
from shared.security import SecureRouter

dpdp_router = SecureRouter(prefix="/identity/dpdp", tags=["dpdp"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class ErasureOut(BaseModel):
    status: Literal["none", "pending", "held", "executed", "cancelled"]
    execute_after: datetime | None = None
    requested_at: datetime | None = None
    # deliberately NOT hold_reasons: a hold names another module's business
    # state ("directory:open_dispute"), which is staff context, not something
    # to hand back over the counter. The user is told it is under review.


class RevealOut(BaseModel):
    revealed_at: datetime
    business_name: str | None
    source: str


class RevealsOut(BaseModel):
    items: list[RevealOut]


@dpdp_router.get("/export", dependencies=[require_permission("profile.read")])
async def export_my_data(
    principal: PrincipalDep, session: SessionDep, request: Request
) -> Response:
    """A JSON archive of everything, as a download.

    Audited: a data-access right that leaves no trace of being exercised
    cannot be shown to have been honoured.
    """
    archive = await build_export(session, principal.user_id)
    user = await session.get(User, principal.user_id)
    await audit(
        session,
        action="dpdp.export",
        actor_user_id=principal.user_id,
        target_type="user",
        target_id=user.agri_id if user else None,
        metadata={"sections": archive["sections_included"]},
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return Response(
        content=json.dumps(archive, indent=2, default=str),
        media_type="application/json",
        headers={
            "content-disposition": f'attachment; filename="agriid-data-{stamp}.json"',
            # one person's entire record: no shared cache may hold it
            "cache-control": "private, no-store",
        },
    )


@dpdp_router.get("/erasure", dependencies=[require_permission("profile.read")])
async def my_erasure_request(principal: PrincipalDep, session: SessionDep) -> ErasureOut:
    row = await open_request(session, principal.user_id)
    if row is None:
        return ErasureOut(status="none")
    return ErasureOut(
        status=row.status,  # type: ignore[arg-type]
        execute_after=row.execute_after,
        requested_at=row.created_at,
    )


@dpdp_router.post("/erasure", dependencies=[require_permission("profile.write")])
async def request_my_erasure(
    principal: PrincipalDep, session: SessionDep, request: Request
) -> ErasureOut:
    """Idempotent: asking twice returns the same request. A second tap is the
    same wish, and duplicating it would give staff two rows for one decision."""
    row = await request_erasure(session, principal.user_id)
    await audit(
        session,
        action="dpdp.erasure_requested",
        actor_user_id=principal.user_id,
        target_type="erasure_request",
        target_id=str(row.id),
        metadata={"execute_after": row.execute_after.isoformat()},
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return ErasureOut(
        status=row.status,  # type: ignore[arg-type]
        execute_after=row.execute_after,
        requested_at=row.created_at,
    )


@dpdp_router.delete("/erasure", dependencies=[require_permission("profile.write")])
async def withdraw_my_erasure(
    principal: PrincipalDep, session: SessionDep, request: Request
) -> ErasureOut:
    try:
        row = await cancel_erasure(session, principal.user_id)
    except ErasureError as exc:
        raise HTTPException(status_code=404, detail=exc.code) from exc
    await audit(
        session,
        action="dpdp.erasure_withdrawn",
        actor_user_id=principal.user_id,
        target_type="erasure_request",
        target_id=str(row.id),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return ErasureOut(status="cancelled", requested_at=row.created_at)


@dpdp_router.get("/reveals", dependencies=[require_permission("profile.read")])
async def my_contact_reveals(principal: PrincipalDep, session: SessionDep) -> RevealsOut:
    """Who was shown your contact details, and when.

    The log records THAT a reveal happened, never the value revealed - the
    owning table is append-only by grant and must never gain a phone column
    (D18). Read through the module seam; identity does not touch directory's
    tables.
    """
    records = await dpdp.reveal_log(session, principal.user_id)
    return RevealsOut(
        items=[
            RevealOut(revealed_at=r.revealed_at, business_name=r.business_name, source=r.source)
            for r in records
        ]
    )
