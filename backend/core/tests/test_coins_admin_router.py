"""Coins ADMIN API (D13 Task 14): rules CRUD (flag-gated), dual-confirm manual
adjust (audit-logged), abuse queue with void-via-compensating-entries.

Auth is ROLE-gated (not permission-gated): coins must never import
modules.identity (import-linter independence contract), so admin_router reads
request.state.principal.roles directly, mirroring modules/coins/router.py's
principal pattern rather than modules/identity/admin_router.py's
require_permission.

Redis-dependent tests (dual-confirm token storage, audit publish on void)
request the `otp_redis` fixture purely for its side effect of pointing
shared.cache.get_redis() at the flushed test redis DB; they SKIP (not fail)
when redis is unreachable, same as other redis-backed suites.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.coins import referrals, service
from modules.coins.models import AbuseFlag, LedgerEntry, Rule
from shared.db import get_session
from shared.flags import FeatureFlag, reset_flag_cache
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 7, 13, tzinfo=UTC)


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...]) -> None:
        self.user_id = user_id
        self.roles = roles


@pytest.fixture
async def api(
    db_session: AsyncSession,
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession, dict[str, _Principal]]]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    state: dict[str, _Principal] = {"principal": _Principal(uuid.uuid4(), ())}

    async def _resolver(request: Request, session: AsyncSession) -> object:
        return state["principal"]

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://id.test") as client:
        yield client, db_session, state


def _admin(state: dict[str, _Principal], *roles: str) -> uuid.UUID:
    admin_id = uuid.uuid4()
    state["principal"] = _Principal(admin_id, roles)
    return admin_id


# --- rules -------------------------------------------------------------


async def test_rules_list_requires_super_admin(
    api: tuple[httpx.AsyncClient, AsyncSession, dict[str, _Principal]],
) -> None:
    http, _session, state = api
    _admin(state, "staff")
    assert (await http.get("/admin/coins/rules")).status_code == 403

    _admin(state, "super_admin")
    response = await http.get("/admin/coins/rules")
    assert response.status_code == 200
    codes = {row["code"] for row in response.json()}
    assert "daily_visit" in codes


async def test_rule_edit_blocked_when_flag_off_then_enabled(
    api: tuple[httpx.AsyncClient, AsyncSession, dict[str, _Principal]],
) -> None:
    http, session, state = api
    _admin(state, "super_admin")

    blocked = await http.put("/admin/coins/rules/daily_visit", json={"amount": 9})
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "rules_admin_disabled"

    await session.execute(
        update(FeatureFlag).where(FeatureFlag.key == "coins_rules_admin").values(enabled=True)
    )
    await session.flush()
    reset_flag_cache()

    allowed = await http.put("/admin/coins/rules/daily_visit", json={"amount": 9})
    assert allowed.status_code == 200
    assert allowed.json()["amount"] == 9

    rule = await session.get(Rule, "daily_visit")
    assert rule is not None and rule.amount == 9


async def test_rule_edit_unknown_code_404(
    api: tuple[httpx.AsyncClient, AsyncSession, dict[str, _Principal]],
) -> None:
    http, session, state = api
    _admin(state, "super_admin")
    await session.execute(
        update(FeatureFlag).where(FeatureFlag.key == "coins_rules_admin").values(enabled=True)
    )
    await session.flush()
    reset_flag_cache()
    response = await http.put("/admin/coins/rules/does_not_exist", json={"amount": 5})
    assert response.status_code == 404
    assert response.json()["detail"] == "unknown_rule"


# --- manual adjust (dual confirm) --------------------------------------


async def test_manual_adjust_is_two_step_and_idempotent(
    api: tuple[httpx.AsyncClient, AsyncSession, dict[str, _Principal]],
    otp_redis: Redis,
) -> None:
    http, session, state = api
    _admin(state, "super_admin")
    target = uuid.uuid4()

    step1 = await http.post(
        "/admin/coins/adjust",
        json={"user_id": str(target), "delta": 500, "reason_note": "goodwill"},
    )
    assert step1.status_code == 200
    token = step1.json()["confirmation_token"]
    assert await service.balance(session, target) == 0  # nothing written yet

    confirmed = await http.post("/admin/coins/adjust/confirm", json={"confirmation_token": token})
    assert confirmed.status_code == 200
    assert confirmed.json()["balance"] == 500
    assert await service.balance(session, target) == 500

    replay = await http.post("/admin/coins/adjust/confirm", json={"confirmation_token": token})
    assert replay.status_code == 400
    assert replay.json()["detail"] == "invalid_or_expired_token"
    assert await service.balance(session, target) == 500  # unchanged


async def test_manual_adjust_requires_super_admin(
    api: tuple[httpx.AsyncClient, AsyncSession, dict[str, _Principal]],
) -> None:
    http, _session, state = api
    _admin(state, "staff")
    response = await http.post(
        "/admin/coins/adjust",
        json={"user_id": str(uuid.uuid4()), "delta": 10, "reason_note": "x"},
    )
    assert response.status_code == 403


async def test_manual_adjust_rejects_zero_delta(
    api: tuple[httpx.AsyncClient, AsyncSession, dict[str, _Principal]],
) -> None:
    http, _session, state = api
    _admin(state, "super_admin")
    response = await http.post(
        "/admin/coins/adjust",
        json={"user_id": str(uuid.uuid4()), "delta": 0, "reason_note": "x"},
    )
    assert response.status_code == 422


async def test_manual_adjust_confirm_unknown_token(
    api: tuple[httpx.AsyncClient, AsyncSession, dict[str, _Principal]],
    otp_redis: Redis,
) -> None:
    http, _session, state = api
    _admin(state, "super_admin")
    response = await http.post(
        "/admin/coins/adjust/confirm", json={"confirmation_token": "bogus-token"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_or_expired_token"


# --- abuse queue + void via compensating entries -----------------------


async def test_abuse_list_requires_staff_or_super_admin(
    api: tuple[httpx.AsyncClient, AsyncSession, dict[str, _Principal]],
) -> None:
    http, session, state = api
    _admin(state, "farmer")
    assert (await http.get("/admin/coins/abuse")).status_code == 403

    referrer, referee = uuid.uuid4(), uuid.uuid4()
    code = await referrals.get_or_create_code(session, referrer)
    referral = await referrals.attribute(
        session, referee_id=referee, code=code, device_fingerprint=None, phone_prefix=None
    )
    assert referral is not None
    session.add(AbuseFlag(referral_id=referral.id, cluster_reason="device"))
    await session.flush()

    _admin(state, "staff")
    response = await http.get("/admin/coins/abuse")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


async def test_void_uses_compensating_entries_and_preserves_originals(
    api: tuple[httpx.AsyncClient, AsyncSession, dict[str, _Principal]],
    otp_redis: Redis,
) -> None:
    http, session, state = api
    referrer, referee = uuid.uuid4(), uuid.uuid4()
    code = await referrals.get_or_create_code(session, referrer)
    referral = await referrals.attribute(
        session, referee_id=referee, code=code, device_fingerprint=None, phone_prefix=None
    )
    assert referral is not None
    await referrals.maybe_reward(session, referee_id=referee, now=NOW)
    assert await service.balance(session, referrer) == 250
    assert await service.balance(session, referee) == 100

    flag = AbuseFlag(referral_id=referral.id, cluster_reason="device")
    session.add(flag)
    await session.flush()

    admin_id = _admin(state, "super_admin")
    response = await http.post(f"/admin/coins/abuse/{flag.id}/void")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "voided"
    assert body["reversed_count"] == 2

    assert await service.balance(session, referrer) == 0
    assert await service.balance(session, referee) == 0

    await session.refresh(referral)
    await session.refresh(flag)
    assert referral.status == "voided"
    assert referral.voided_at is not None
    assert flag.status == "voided"
    assert flag.reviewed_by == admin_id
    assert flag.reviewed_at is not None

    original = (
        await session.scalars(
            select(LedgerEntry).where(
                LedgerEntry.ref_id == str(referral.id),
                LedgerEntry.reason_code.in_(("referral_referrer", "referral_referee")),
            )
        )
    ).all()
    assert len(original) == 2  # append-only: originals untouched

    compensating = (
        await session.scalars(select(LedgerEntry).where(LedgerEntry.reason_code == "compensation"))
    ).all()
    assert len(compensating) == 2
    assert {e.delta for e in compensating} == {-250, -100}


async def test_void_unknown_flag_404(
    api: tuple[httpx.AsyncClient, AsyncSession, dict[str, _Principal]],
    otp_redis: Redis,
) -> None:
    http, _session, state = api
    _admin(state, "super_admin")
    response = await http.post(f"/admin/coins/abuse/{uuid.uuid4()}/void")
    assert response.status_code == 404


async def test_void_is_not_double_applied_on_second_call(
    api: tuple[httpx.AsyncClient, AsyncSession, dict[str, _Principal]],
    otp_redis: Redis,
) -> None:
    """A second void on an already-resolved (non-"open") flag short-circuits:
    it returns 200 with reversed_count=0 and does not reverse anything again,
    re-mark the referral/flag, or publish another audit event."""
    http, session, state = api
    referrer, referee = uuid.uuid4(), uuid.uuid4()
    code = await referrals.get_or_create_code(session, referrer)
    referral = await referrals.attribute(
        session, referee_id=referee, code=code, device_fingerprint=None, phone_prefix=None
    )
    assert referral is not None
    await referrals.maybe_reward(session, referee_id=referee, now=NOW)
    flag = AbuseFlag(referral_id=referral.id, cluster_reason="device")
    session.add(flag)
    await session.flush()

    _admin(state, "super_admin")
    first = await http.post(f"/admin/coins/abuse/{flag.id}/void")
    assert first.status_code == 200
    assert first.json()["reversed_count"] == 2
    second = await http.post(f"/admin/coins/abuse/{flag.id}/void")
    assert second.status_code == 200
    assert second.json()["reversed_count"] == 0  # already-resolved: no reprocessing
    assert await service.balance(session, referrer) == 0
    assert await service.balance(session, referee) == 0

    compensating = (
        await session.scalars(select(LedgerEntry).where(LedgerEntry.reason_code == "compensation"))
    ).all()
    assert len(compensating) == 2  # second call did not create more compensation rows


async def test_adjust_confirm_insufficient_balance_409(
    api: tuple[httpx.AsyncClient, AsyncSession, dict[str, _Principal]],
    otp_redis: Redis,
) -> None:
    """A negative manual adjust larger than the target's balance is rejected
    at confirm time with 409; nothing is written (no ledger row, no balance
    change) - the intent token is still consumed (single-use getdel)."""
    http, session, state = api
    _admin(state, "super_admin")
    target = uuid.uuid4()
    assert await service.balance(session, target) == 0

    step1 = await http.post(
        "/admin/coins/adjust",
        json={"user_id": str(target), "delta": -500, "reason_note": "clawback"},
    )
    assert step1.status_code == 200
    token = step1.json()["confirmation_token"]

    confirmed = await http.post("/admin/coins/adjust/confirm", json={"confirmation_token": token})
    assert confirmed.status_code == 409
    assert confirmed.json()["detail"] == "insufficient_balance"

    assert await service.balance(session, target) == 0
    entries = (
        await session.scalars(
            select(LedgerEntry).where(
                LedgerEntry.user_id == target, LedgerEntry.reason_code == "manual_adjust"
            )
        )
    ).all()
    assert len(entries) == 0


async def test_void_insufficient_balance_rolls_back_atomically(
    api: tuple[httpx.AsyncClient, AsyncSession, dict[str, _Principal]],
    otp_redis: Redis,
) -> None:
    """If the referrer already spent their referral reward, voiding must be
    whole-or-nothing: the -250 referrer reversal overdraws, so the savepoint
    must roll back the referee's reversal (which would have succeeded first)
    too, along with the referral/flag status changes - even though nothing
    ever touches the same row twice."""
    http, session, state = api
    referrer, referee = uuid.uuid4(), uuid.uuid4()
    code = await referrals.get_or_create_code(session, referrer)
    referral = await referrals.attribute(
        session, referee_id=referee, code=code, device_fingerprint=None, phone_prefix=None
    )
    assert referral is not None
    await referrals.maybe_reward(session, referee_id=referee, now=NOW)
    assert await service.balance(session, referrer) == 250
    assert await service.balance(session, referee) == 100

    await service.redeem(
        session,
        user_id=referrer,
        amount=250,
        reason_code="spend",
        ref_id=None,
        idempotency_key=f"spend:{referrer}",
    )
    assert await service.balance(session, referrer) == 0

    flag = AbuseFlag(referral_id=referral.id, cluster_reason="device")
    session.add(flag)
    await session.flush()

    _admin(state, "super_admin")
    response = await http.post(f"/admin/coins/abuse/{flag.id}/void")
    assert response.status_code == 409
    assert response.json()["detail"] == "cannot_void_insufficient_balance"

    compensating = (
        await session.scalars(select(LedgerEntry).where(LedgerEntry.reason_code == "compensation"))
    ).all()
    assert len(compensating) == 0  # whole-void atomicity: zero compensation rows

    await session.refresh(referral)
    await session.refresh(flag)
    assert referral.status == "rewarded"  # unchanged, not voided
    assert flag.status == "open"  # unchanged, not voided
