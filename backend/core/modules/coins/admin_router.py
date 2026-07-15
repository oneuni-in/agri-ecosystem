"""Coins ADMIN API (D13.E): rules CRUD (flag-gated), dual-confirm manual
balance adjust (audit-logged), abuse queue with void-via-compensating-entries.

Auth is ROLE-gated, not permission-gated: modules.coins must never import
modules.identity (import-linter independence contract enforces this), so
`require_permission` is unavailable here. Every handler reads
`request.state.principal.roles` (a `tuple[str, ...]` set by `require_auth` via
shared.security) through the local `_require_role` helper below - mirrors the
principal-reading pattern already used by modules/coins/router.py.

Never log request bodies (reason_note, balances) - audit events carry ids and
amounts only, which is fine; logger.info/warning of raw bodies is not.
"""

import json
import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.coins import service
from modules.coins.models import AbuseFlag, LedgerEntry, Referral, Rule
from shared.cache import get_redis
from shared.db import get_session
from shared.events import publish
from shared.flags import flag_enabled
from shared.pagination import DEFAULT_PAGE_SIZE, paginate
from shared.security import SecureRouter

admin_router = SecureRouter(prefix="/admin/coins", tags=["coins-admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

SUPER_ADMIN = "super_admin"
STAFF = "staff"

_ADJUST_INTENT_TTL_SECONDS = 300


def _require_role(request: Request, *allowed: str) -> uuid.UUID:
    """Fail-closed role gate. Returns the acting admin's user_id (for audit)."""
    principal = request.state.principal
    roles = getattr(principal, "roles", ())
    if not any(r in roles for r in allowed):
        raise HTTPException(status_code=403, detail="missing_role")
    uid = principal.user_id
    assert isinstance(uid, uuid.UUID)  # narrow Starlette state's Any for mypy
    return uid


# --- schemas -------------------------------------------------------------


class RuleOut(BaseModel):
    code: str
    amount: int
    daily_cap: int | None
    weekly_cap: int | None
    total_cap: int | None
    active: bool
    valid_from: datetime | None
    valid_to: datetime | None


def _rule_out(rule: Rule) -> RuleOut:
    return RuleOut(
        code=rule.code,
        amount=rule.amount,
        daily_cap=rule.daily_cap,
        weekly_cap=rule.weekly_cap,
        total_cap=rule.total_cap,
        active=rule.active,
        valid_from=rule.valid_from,
        valid_to=rule.valid_to,
    )


class RuleUpdateIn(BaseModel):
    amount: Annotated[int, Field(gt=0)] | None = None
    daily_cap: int | None = None
    weekly_cap: int | None = None
    total_cap: int | None = None
    active: bool | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class AdjustIn(BaseModel):
    user_id: uuid.UUID
    delta: int
    reason_note: Annotated[str, Field(min_length=1)]

    @field_validator("delta")
    @classmethod
    def _nonzero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("delta must be non-zero")
        return value


class AdjustTokenOut(BaseModel):
    confirmation_token: str


class AdjustConfirmIn(BaseModel):
    confirmation_token: str


class AdjustConfirmOut(BaseModel):
    balance: int


class AbuseFlagOut(BaseModel):
    id: uuid.UUID
    referral_id: uuid.UUID
    cluster_reason: str
    status: str
    details: dict[str, Any]
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime


def _abuse_flag_out(flag: AbuseFlag) -> AbuseFlagOut:
    return AbuseFlagOut(
        id=flag.id,
        referral_id=flag.referral_id,
        cluster_reason=flag.cluster_reason,
        status=flag.status,
        details=flag.details,
        reviewed_by=flag.reviewed_by,
        reviewed_at=flag.reviewed_at,
        created_at=flag.created_at,
    )


class AbusePageOut(BaseModel):
    items: list[AbuseFlagOut]
    next_cursor: str | None = None


class VoidOut(BaseModel):
    status: str
    reversed_count: int


# --- rules CRUD (flag-gated) ---------------------------------------------


@admin_router.get("/rules")
async def list_rules(request: Request, session: SessionDep) -> list[RuleOut]:
    _require_role(request, SUPER_ADMIN)
    rows = (await session.scalars(select(Rule).order_by(Rule.code))).all()
    return [_rule_out(rule) for rule in rows]


@admin_router.put("/rules/{code}")
async def update_rule(
    code: str, body: RuleUpdateIn, request: Request, session: SessionDep
) -> RuleOut:
    _require_role(request, SUPER_ADMIN)
    if not await flag_enabled("coins_rules_admin", session=session):
        raise HTTPException(status_code=403, detail="rules_admin_disabled")
    rule = await session.get(Rule, code)
    if rule is None:
        raise HTTPException(status_code=404, detail="unknown_rule")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(rule, field, value)
    await session.flush()
    return _rule_out(rule)


# --- manual adjust: dual-confirm, audit-logged ---------------------------


def _intent_key(token: str) -> str:
    return f"coins:adjust:{token}"


@admin_router.post("/adjust")
async def adjust_step1(body: AdjustIn, request: Request) -> AdjustTokenOut:
    """Step 1: writes NOTHING to the ledger. Stores the intent in Redis
    (short TTL, single-use-by-getdel on confirm) and hands back an opaque
    token the caller must resubmit to actually apply the adjustment."""
    admin_id = _require_role(request, SUPER_ADMIN)
    token = secrets.token_urlsafe(16)
    intent = {
        "user_id": str(body.user_id),
        "delta": body.delta,
        "reason_note": body.reason_note,
        "admin_id": str(admin_id),
    }
    await get_redis().set(_intent_key(token), json.dumps(intent), ex=_ADJUST_INTENT_TTL_SECONDS)
    return AdjustTokenOut(confirmation_token=token)


@admin_router.post("/adjust/confirm")
async def adjust_confirm(
    body: AdjustConfirmIn, request: Request, session: SessionDep
) -> AdjustConfirmOut:
    """Step 2: single-use (getdel) application of a pending manual adjust
    intent as a normal ledger entry via service.record_entry (never a direct
    ledger write), then an audit event."""
    _require_role(request, SUPER_ADMIN)
    raw = await get_redis().getdel(_intent_key(body.confirmation_token))
    if raw is None:
        raise HTTPException(status_code=400, detail="invalid_or_expired_token")
    intent = json.loads(raw)
    user_id = uuid.UUID(intent["user_id"])
    delta = int(intent["delta"])
    admin_id = intent["admin_id"]
    try:
        # ref_id/audit use the intent's stored admin_id (the initiator), not the
        # confirmer: dual-confirm is a two-STEP accidental-adjustment guard, not
        # a two-PERSON approval control - the confirmer is independently
        # role-checked above via _require_role.
        await service.record_entry(
            session,
            user_id=user_id,
            delta=delta,
            reason_code="manual_adjust",
            ref_type="admin",
            ref_id=admin_id,
            idempotency_key=f"manual_adjust:{body.confirmation_token}",
        )
    except service.InsufficientBalanceError as exc:
        raise HTTPException(status_code=409, detail="insufficient_balance") from exc
    await publish(
        "audit",
        "coins.manual_adjust",
        {
            "admin_id": admin_id,
            "user_id": intent["user_id"],
            "delta": delta,
            "reason_note": intent["reason_note"],
        },
    )
    return AdjustConfirmOut(balance=await service.balance(session, user_id))


# --- abuse queue: void via compensating entries only ----------------------


@admin_router.get("/abuse")
async def list_abuse(
    request: Request,
    session: SessionDep,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = DEFAULT_PAGE_SIZE,
) -> AbusePageOut:
    _require_role(request, SUPER_ADMIN, STAFF)
    page = await paginate(
        session, select(AbuseFlag).where(AbuseFlag.status == "open"), cursor=cursor, limit=limit
    )
    return AbusePageOut(
        items=[_abuse_flag_out(flag) for flag in page.items], next_cursor=page.next_cursor
    )


@admin_router.post("/abuse/{flag_id}/void")
async def void_abuse(flag_id: uuid.UUID, request: Request, session: SessionDep) -> VoidOut:
    """Void via COMPENSATING ENTRIES ONLY - never delete or mutate original
    ledger rows. Reverses exactly the referral awards that were actually
    granted (handles the capped-referrer case where no referrer entry
    exists). If a reversal would overdraw a spender (they already redeemed
    the coins), the whole request rolls back and nothing is voided."""
    admin_id = _require_role(request, SUPER_ADMIN, STAFF)
    flag = await session.get(AbuseFlag, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="unknown_flag")
    if flag.status != "open":
        # Already resolved (voided/reviewed): re-void is idempotent (200) but
        # must not reverse anything again, re-mark the referral/flag, or
        # publish another audit event - that would duplicate the audit trail
        # and re-process a settled case.
        return VoidOut(status="voided", reversed_count=0)
    referral = await session.get(Referral, flag.referral_id)
    if referral is None:
        raise HTTPException(status_code=404, detail="unknown_referral")

    awarded = (
        await session.scalars(
            select(LedgerEntry).where(
                LedgerEntry.ref_id == str(referral.id),
                LedgerEntry.reason_code.in_(("referral_referrer", "referral_referee")),
            )
        )
    ).all()
    reversed_count = 0
    now = datetime.now(UTC)
    # The whole void (compensating entries + referral/flag status) is wrapped
    # in one savepoint so it is SELF-atomic regardless of how the caller
    # manages the outer transaction: if any reversal overdraws, we roll back
    # this savepoint - discarding any compensation entries already applied AND
    # the status changes - before raising 409. service.record_entry's own
    # inner begin_nested() calls stack fine inside this outer savepoint.
    void_sp = await session.begin_nested()
    try:
        for entry in awarded:
            await service.record_entry(
                session,
                user_id=entry.user_id,
                delta=-entry.delta,
                reason_code="compensation",
                ref_type="void",
                ref_id=str(referral.id),
                idempotency_key=f"compensation:{entry.id}",
            )
            reversed_count += 1

        referral.status = "voided"
        referral.voided_at = now
        flag.status = "voided"
        flag.reviewed_by = admin_id
        flag.reviewed_at = now
        await session.flush()
    except service.InsufficientBalanceError as exc:
        await void_sp.rollback()
        raise HTTPException(status_code=409, detail="cannot_void_insufficient_balance") from exc
    else:
        await void_sp.commit()

    await publish(
        "audit",
        "coins.referral_void",
        {"admin_id": str(admin_id), "referral_id": str(referral.id), "flag_id": str(flag_id)},
    )
    return VoidOut(status="voided", reversed_count=reversed_count)
