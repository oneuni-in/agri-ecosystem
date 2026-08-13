"""Payments read surface (U3) — DISPLAY ONLY.

The admin console needs to SEE Razorpay activity before KYC: the append-only
ad-revenue ledger (billing.ledger_entries) and the raw webhook log
(billing.payment_events). This router is read-only by construction — it has no
POST/PUT/DELETE, and both tables are append-only by grant (the app role has no
UPDATE/DELETE), so NO admin action can alter a row even in principle. All the
money-path WRITES (charge, refund, credit, reconcile) stay out of scope (U3
OUT OF BOUNDS 3) and live on the flag-gated /billing/admin router.

Mounted under /admin/payments (not /billing/admin) so it flows through the
web-admin BFF's /api/admin proxy like every other admin surface. Gated by the
shared permission catalog (payments.read) — no write permission is defined for
this surface on purpose.

Auth is permission-gated via shared.authz (which imports no module), so this
does not breach billing's import independence."""

from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.billing.models import BillingLedgerEntry, PaymentEvent
from modules.billing.schemas import (
    PaymentEventPage,
    PaymentEventRowOut,
    PaymentLedgerPage,
    PaymentLedgerRowOut,
    format_paise,
)
from shared.authz import require_permission
from shared.db import get_session
from shared.pagination import DEFAULT_PAGE_SIZE, InvalidCursorError, paginate
from shared.security import SecureRouter

admin_router = SecureRouter(prefix="/admin/payments", tags=["payments-admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]


@admin_router.get(
    "/ledger",
    dependencies=[require_permission("payments.read")],
)
async def list_ledger(
    request: Request,
    session: SessionDep,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> PaymentLedgerPage:
    """The append-only ad-revenue ledger, newest first. DISPLAY ONLY."""
    try:
        page = await paginate(
            session, select(BillingLedgerEntry), cursor=cursor, limit=limit, descending=True
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return PaymentLedgerPage(
        items=[
            PaymentLedgerRowOut(
                id=row.id,
                entry_type=row.entry_type,
                amount_display=format_paise(row.amount_paise, row.currency),
                amount_paise=row.amount_paise,
                currency=row.currency,
                campaign_id=row.campaign_id,
                business_id=row.business_id,
                razorpay_payment_id=row.razorpay_payment_id,
                created_at=row.created_at,
            )
            for row in page.items
        ],
        next_cursor=page.next_cursor,
    )


@admin_router.get(
    "/events",
    dependencies=[require_permission("payments.read")],
)
async def list_events(
    request: Request,
    session: SessionDep,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> PaymentEventPage:
    """The raw Razorpay webhook log, newest first — every row is a
    signature-verified transaction (a bad signature 400s before it persists).
    DISPLAY ONLY."""
    try:
        page = await paginate(
            session, select(PaymentEvent), cursor=cursor, limit=limit, descending=True
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return PaymentEventPage(
        items=[
            PaymentEventRowOut(
                id=row.id,
                provider=row.provider,
                event_type=row.event_type,
                provider_event_id=row.provider_event_id,
                outcome=row.outcome,
                signature_verified=True,
                created_at=row.created_at,
            )
            for row in page.items
        ],
        next_cursor=page.next_cursor,
    )
