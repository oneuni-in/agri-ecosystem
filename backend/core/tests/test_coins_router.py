"""Coins user API: auth-gated balance/history/referral-code (D13.C).

Principal is injected directly via register_principal_resolver (see
test_require_auth.py) rather than a real login flow - coins routes only
need request.state.principal.user_id, not the rest of the session stack."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.coins import service
from modules.coins.models import ReferralCode
from shared.db import get_session
from shared.lookups import register_handle_resolver, reset_lookup_resolvers
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio


class _Principal:
    def __init__(self, user_id: uuid.UUID) -> None:
        self.user_id = user_id
        self.roles = ("user",)


@pytest.fixture
async def api(
    db_session: AsyncSession,
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession, uuid.UUID]]:
    app = create_app()
    user_id = uuid.uuid4()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _resolver(request: Request, session: AsyncSession) -> object:
        return _Principal(user_id)

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://id.test") as client:
        yield client, db_session, user_id


async def test_balance_starts_zero(
    api: tuple[httpx.AsyncClient, AsyncSession, uuid.UUID],
) -> None:
    http, _session, _uid = api
    response = await http.get("/coins/balance")
    assert response.status_code == 200
    assert response.json()["balance"] == 0


async def test_balance_reflects_awards(
    api: tuple[httpx.AsyncClient, AsyncSession, uuid.UUID],
) -> None:
    http, session, uid = api
    await service.record_entry(
        session,
        user_id=uid,
        delta=100,
        reason_code="signup_complete",
        ref_type="rule",
        ref_id="signup_complete",
        idempotency_key=f"s:{uid}",
    )
    response = await http.get("/coins/balance")
    assert response.json()["balance"] == 100


async def test_history_returns_labels(
    api: tuple[httpx.AsyncClient, AsyncSession, uuid.UUID],
) -> None:
    http, session, uid = api
    await service.record_entry(
        session,
        user_id=uid,
        delta=5,
        reason_code="daily_visit",
        ref_type="rule",
        ref_id="d",
        idempotency_key=f"d:{uid}",
    )
    response = await http.get("/coins/history")
    body = response.json()
    assert body["items"][0]["reason_label_key"] == "coins.reason.daily_visit"
    assert body["items"][0]["delta"] == 5


async def test_referral_code_is_stable(
    api: tuple[httpx.AsyncClient, AsyncSession, uuid.UUID],
) -> None:
    http, _session, _uid = api
    first = (await http.get("/coins/referral-code")).json()["code"]
    second = (await http.get("/coins/referral-code")).json()["code"]
    assert first == second
    assert len(first) >= 6


# --- ID-U1: referral code -> inviter handle (the login done screen) ----------
# The handle arrives through shared.lookups, never a join: coins may not read
# identity.users. These tests register a fake resolver for exactly that reason
# - if the seam is ever replaced by a direct import, the import-linter
# contract breaks first and these still pass, which is the point of having
# both.


async def test_resolve_referrer_names_the_code_owner(
    api: tuple[httpx.AsyncClient, AsyncSession, uuid.UUID],
) -> None:
    http, session, _uid = api
    owner_id = uuid.uuid4()
    session.add(ReferralCode(user_id=owner_id, code="OWNERC0DE"))
    await session.flush()
    register_handle_resolver(lambda _s, user_id: _handle_for(user_id, owner_id))
    response = await http.get("/coins/referral/resolve", params={"code": "OWNERC0DE"})
    assert response.status_code == 200
    assert response.json() == {"handle": "murugesan"}


async def test_resolve_referrer_is_silent_on_an_unknown_code(
    api: tuple[httpx.AsyncClient, AsyncSession, uuid.UUID],
) -> None:
    http, _session, _uid = api
    response = await http.get("/coins/referral/resolve", params={"code": "N0SUCHC0"})
    assert response.status_code == 200
    # Not a 404: an unknown code and a code we decline to name must be
    # indistinguishable, or the endpoint becomes a code-existence oracle.
    assert response.json() == {"handle": None}


async def test_resolve_referrer_never_names_you_to_yourself(
    api: tuple[httpx.AsyncClient, AsyncSession, uuid.UUID],
) -> None:
    http, session, uid = api
    session.add(ReferralCode(user_id=uid, code="MYOWNC0DE"))
    await session.flush()
    register_handle_resolver(lambda _s, user_id: _handle_for(user_id, uid))
    response = await http.get("/coins/referral/resolve", params={"code": "MYOWNC0DE"})
    assert response.status_code == 200
    # referrals.attribute refuses a self-referral, so the banner must not
    # imply one is in progress.
    assert response.json() == {"handle": None}


async def test_resolve_referrer_fails_closed_without_a_resolver(
    api: tuple[httpx.AsyncClient, AsyncSession, uuid.UUID],
) -> None:
    http, session, _uid = api
    session.add(ReferralCode(user_id=uuid.uuid4(), code="NORESOLVE"))
    await session.flush()
    reset_lookup_resolvers()
    response = await http.get("/coins/referral/resolve", params={"code": "NORESOLVE"})
    assert response.status_code == 200
    assert response.json() == {"handle": None}


async def _handle_for(user_id: uuid.UUID, expected: uuid.UUID) -> str | None:
    return "murugesan" if user_id == expected else None
