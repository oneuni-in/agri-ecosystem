"""ID-U1 W4 - the three DPDP rights.

The prompt asks for three things specifically: export completeness, erasure
idempotency, and an IDOR attempt on both. All three are here, plus the hold
flow, because "held on an open dispute" is the part of the erasure right that
can silently do the wrong thing.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.dpdp_models import ErasureRequest
from modules.identity.dpdp_service import (
    ERASURE_GRACE_DAYS,
    erase_user,
    execute_due,
    request_erasure,
)
from modules.identity.models import Profile, User
from shared import dpdp
from shared.db import get_session
from tests.test_session_router import UA, _login

pytestmark = pytest.mark.asyncio

PHONE = "+919876533333"
OTHER_PHONE = "+919876544444"


@pytest.fixture
async def api(
    db_session: AsyncSession, otp_redis: Redis
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://id.test", headers=UA
    ) as client:
        yield client, db_session


async def _user(session: AsyncSession, phone: str) -> User:
    user = await session.scalar(select(User).where(User.phone == phone))
    assert user is not None
    return user


# --- export -----------------------------------------------------------------


async def test_export_contains_every_registered_section(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """Completeness, pinned to the REGISTRY rather than to a literal list.

    A module that starts holding user data and forgets to register a provider
    fails here, instead of quietly handing someone a short archive when they
    exercise a legal right.
    """
    http, session = api
    await _login(http, session, phone=PHONE)
    response = await http.get("/identity/dpdp/export")
    assert response.status_code == 200
    body = response.json()
    assert set(body["sections_included"]) == set(dpdp.registered_export_sections())
    assert set(body["data"]) == set(body["sections_included"])
    # the manifest is what lets a reader tell an EMPTY section from a MISSING
    # one - "you have no coins" vs "we did not give you your coins data"
    assert "identity" in body["data"] and "coins" in body["data"]


async def test_export_returns_the_subjects_own_phone_in_full(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    body = (await http.get("/identity/dpdp/export")).json()
    # admin surfaces see last-4 only (D11), but this archive goes to its own
    # subject and a masked copy of your own number is not a data-access right
    assert body["data"]["identity"]["phone"] == PHONE


async def test_export_is_a_private_download_and_never_cached(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    response = await http.get("/identity/dpdp/export")
    assert "attachment" in response.headers["content-disposition"]
    assert "no-store" in response.headers["cache-control"]


async def test_export_carries_no_internal_uuid(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    user = await _user(session, PHONE)
    assert str(user.id) not in (await http.get("/identity/dpdp/export")).text


async def test_export_requires_a_session(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _session = api
    assert (await http.get("/identity/dpdp/export")).status_code == 401


# --- IDOR -------------------------------------------------------------------


async def test_no_dpdp_route_accepts_someone_elses_id(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """The IDOR attempt. There is no user-id parameter to tamper with on any
    of these routes - the endpoints read principal.user_id and nothing else -
    so the attack is to try to introduce one and confirm it is ignored.
    """
    http, session = api
    await _login(http, session, phone=PHONE)
    victim = await _user(session, PHONE)
    # create a second account whose data the attacker wants
    await _login(http, session, phone=OTHER_PHONE)
    attacker = await _user(session, OTHER_PHONE)
    assert victim.id != attacker.id

    # the session is now the attacker's; every attempt to aim at the victim
    for params in (
        {"user_id": str(victim.id)},
        {"agri_id": victim.agri_id},
        {"id": str(victim.id)},
    ):
        body = (await http.get("/identity/dpdp/export", params=params)).json()
        assert body["data"]["identity"]["phone"] == OTHER_PHONE
        assert body["data"]["identity"]["handle"] == attacker.agri_id

    reveals = await http.get("/identity/dpdp/reveals", params={"user_id": str(victim.id)})
    assert reveals.status_code == 200

    # and an erasure aimed at the victim erases nothing of theirs
    await http.post("/identity/dpdp/erasure", params={"user_id": str(victim.id)})
    row = await session.scalar(select(ErasureRequest).where(ErasureRequest.user_id == victim.id))
    assert row is None


# --- erasure ----------------------------------------------------------------


async def test_erasure_request_is_idempotent(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """Asking twice is the same wish, not two decisions for staff to make."""
    http, session = api
    await _login(http, session, phone=PHONE)
    first = (await http.post("/identity/dpdp/erasure")).json()
    second = (await http.post("/identity/dpdp/erasure")).json()
    assert first["requested_at"] == second["requested_at"]
    assert first["execute_after"] == second["execute_after"]
    user = await _user(session, PHONE)
    rows = (
        await session.scalars(select(ErasureRequest).where(ErasureRequest.user_id == user.id))
    ).all()
    assert len(rows) == 1


async def test_erasure_waits_out_its_grace_window(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    body = (await http.post("/identity/dpdp/erasure")).json()
    assert body["status"] == "pending"
    execute_after = datetime.fromisoformat(body["execute_after"])
    assert execute_after > datetime.now(UTC) + timedelta(days=ERASURE_GRACE_DAYS - 1)
    # nothing is due yet, so a tick right now must not touch it
    result = await execute_due(session)
    assert result["executed"] == [] and result["considered"] == 0
    user = await _user(session, PHONE)
    assert user.status == "active"


async def test_user_can_withdraw_before_the_grace_elapses(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    await http.post("/identity/dpdp/erasure")
    assert (await http.delete("/identity/dpdp/erasure")).json()["status"] == "cancelled"
    assert (await http.get("/identity/dpdp/erasure")).json()["status"] == "none"
    # and the withdrawal is durable: a due tick finds nothing open
    assert (await execute_due(session, now=datetime.now(UTC) + timedelta(days=99)))[
        "considered"
    ] == 0


async def test_an_open_dispute_holds_the_erasure_instead_of_running_it(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """The collides-with-a-dispute case. Held is not a failure state - it is
    the system refusing to do something irreversible while a question is open.
    """
    http, session = api
    await _login(http, session, phone=PHONE)
    user = await _user(session, PHONE)
    await http.post("/identity/dpdp/erasure")

    async def _always_holds(_s: AsyncSession, _u: uuid.UUID) -> str | None:
        return "open_dispute"

    dpdp.register_erasure_hold_provider("pytest", _always_holds)
    try:
        result = await execute_due(session, now=datetime.now(UTC) + timedelta(days=99))
    finally:
        dpdp._hold_providers.pop("pytest", None)
    assert result["executed"] == [] and len(result["held"]) == 1
    row = await session.scalar(select(ErasureRequest).where(ErasureRequest.user_id == user.id))
    assert row is not None and row.status == "held"
    assert "pytest:open_dispute" in (row.hold_reasons or "")
    # and crucially the account is untouched
    refreshed = await session.get(User, user.id)
    assert refreshed is not None and refreshed.status == "active"


async def test_a_provider_that_raises_is_itself_a_hold(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """Fail-closed. An unanswerable question about an irreversible action
    resolves to "ask a human", never to "go ahead"."""
    http, session = api
    await _login(http, session, phone=PHONE)
    await http.post("/identity/dpdp/erasure")

    async def _broken(_s: AsyncSession, _u: uuid.UUID) -> str | None:
        raise RuntimeError("module down")

    dpdp.register_erasure_hold_provider("pytest", _broken)
    try:
        result = await execute_due(session, now=datetime.now(UTC) + timedelta(days=99))
    finally:
        dpdp._hold_providers.pop("pytest", None)
    assert result["executed"] == [] and len(result["held"]) == 1
    user = await _user(session, PHONE)
    assert user.status == "active"


async def test_a_held_request_can_still_be_withdrawn(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """A hold is a reason not to delete someone. It is never a reason to make
    them stay deleted."""
    http, session = api
    await _login(http, session, phone=PHONE)
    user = await _user(session, PHONE)
    row = await request_erasure(session, user.id)
    row.status = "held"
    row.hold_reasons = "directory:open_report"
    await session.flush()
    assert (await http.delete("/identity/dpdp/erasure")).status_code == 200
    assert (await http.get("/identity/dpdp/erasure")).json()["status"] == "none"


async def test_execution_scrubs_the_person_but_keeps_the_row(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    await _login(http, session, phone=PHONE)
    await http.patch("/identity/profile", json={"name": "Murugesan"})
    user = await _user(session, PHONE)
    user_id = user.id
    old_handle = user.agri_id

    await erase_user(session, user_id)

    erased = await session.get(User, user_id)
    assert erased is not None, "the row must survive - a ledger cannot lose its subject"
    assert erased.status == "deleted"
    assert erased.phone != PHONE and PHONE not in erased.phone
    assert erased.agri_id != old_handle
    profile = await session.scalar(select(Profile).where(Profile.user_id == user_id))
    assert profile is not None and profile.name is None and profile.interests == []


async def test_erasure_is_idempotent_at_execution_too(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """Running the job twice over the same request must not double-erase or
    resurrect anything - reruns happen (a crashed tick, a retried deploy)."""
    http, session = api
    await _login(http, session, phone=PHONE)
    await http.post("/identity/dpdp/erasure")
    later = datetime.now(UTC) + timedelta(days=99)
    first = await execute_due(session, now=later)
    second = await execute_due(session, now=later)
    assert len(first["executed"]) == 1
    assert second["executed"] == [] and second["considered"] == 0
    erased = await session.get(User, await _erased_id(session))
    assert erased is not None and erased.status == "deleted"


async def _erased_id(session: AsyncSession) -> uuid.UUID:
    row = await session.scalar(
        select(ErasureRequest).where(ErasureRequest.status == "executed").limit(1)
    )
    assert row is not None
    return row.user_id


async def test_an_unwired_registry_holds_instead_of_erasing(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """Regression, and a real incident rather than a hypothetical.

    scripts/dpdp_erasure_job.py imported execute_due directly and never ran
    the dependency wiring, so no hold provider was registered. `erasure_holds`
    returned [] - meaning "nobody objected" - when the truth was "nobody was
    asked", and the first run of the job erased a dev account that owned five
    live businesses.

    Two things now prevent it: the job calls wire_dependencies(), and this -
    an empty hold registry is itself a hold.
    """
    http, session = api
    await _login(http, session, phone=PHONE)
    user = await _user(session, PHONE)
    await http.post("/identity/dpdp/erasure")

    saved = dict(dpdp._hold_providers)
    dpdp._hold_providers.clear()
    try:
        result = await execute_due(session, now=datetime.now(UTC) + timedelta(days=99))
    finally:
        dpdp._hold_providers.update(saved)

    assert result["executed"] == [], "an unwired registry must never erase anyone"
    assert len(result["held"]) == 1
    row = await session.scalar(select(ErasureRequest).where(ErasureRequest.user_id == user.id))
    assert row is not None and row.status == "held"
    assert "registry:unwired" in (row.hold_reasons or "")
    refreshed = await session.get(User, user.id)
    assert refreshed is not None and refreshed.status == "active"
