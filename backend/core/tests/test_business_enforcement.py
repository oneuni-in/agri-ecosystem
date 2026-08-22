"""Business enforcement (M1.5.B/E): suspend / disable / reinstate.

Non-negotiable 2: a suspended business vanishes from covers() + search and
its profile turns into a 410, while the owner still sees it (with the
reason). Non-negotiable 3: a disabled business locks the owner console.
Non-negotiable 4: every enforcement action writes an audit row and
reinstate restores the prior state."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import service
from modules.directory.models import Business, BusinessCoverage
from shared.audit import AuditEntry
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

OWNER = uuid.uuid4()
STAFF = uuid.uuid4()
PINCODE = "641001"


class _Principal:
    def __init__(self, user_id: uuid.UUID, roles: tuple[str, ...] = ("user",)) -> None:
        self.user_id = user_id
        self.roles = roles


def _as(user_id: uuid.UUID, *roles: str) -> dict[str, str]:
    headers = {"x-test-user": str(user_id)}
    if roles:
        headers["x-test-roles"] = ",".join(roles)
    return headers


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []

    async def fake_publish(stream: str, event_type: str, payload: dict[str, Any]) -> str:
        events.append((event_type, payload))
        return "1-0"

    monkeypatch.setattr("modules.directory.admin_router.publish", fake_publish)
    return events


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _resolver(request: Request, session: AsyncSession) -> object | None:
        header = request.headers.get("x-test-user")
        if header is None:
            return None
        roles = tuple((request.headers.get("x-test-roles") or "user").split(","))
        return _Principal(uuid.UUID(header), roles)

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        yield client, db_session


async def _business(session: AsyncSession, *, name: str = "Enforced Dairy") -> Business:
    business = await service.create_business(
        session, owner_user_id=OWNER, name=name, type_="vendor", primary_pincode=PINCODE
    )
    session.add(BusinessCoverage(business_id=business.id, pincode=PINCODE))
    await session.flush()
    return business


async def _covers_ids(http: httpx.AsyncClient) -> set[str]:
    resp = await http.get(f"/directory/covers/{PINCODE}")
    assert resp.status_code == 200
    return {item["id"] for item in resp.json()["items"]}


# --- suspend (non-negotiable 2) --------------------------------------------


async def test_suspend_requires_staff(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    b = await _business(session)
    resp = await http.post(
        f"/admin/directory/businesses/{b.id}/suspend",
        json={"reason": "fake listing"},
        headers=_as(OWNER),
    )
    assert resp.status_code == 403


async def test_suspend_reason_required(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    b = await _business(session)
    resp = await http.post(
        f"/admin/directory/businesses/{b.id}/suspend", json={}, headers=_as(STAFF, "staff")
    )
    assert resp.status_code == 422


async def test_suspend_hides_everywhere_but_owner(
    api: tuple[httpx.AsyncClient, AsyncSession],
    published: list[tuple[str, dict[str, Any]]],
    tn_geo_sample: None,
) -> None:
    http, session = api
    b = await _business(session)
    slug = b.slug
    assert str(b.id) in await _covers_ids(http)

    resp = await http.post(
        f"/admin/directory/businesses/{b.id}/suspend",
        json={"reason": "reported as fake listing"},
        headers=_as(STAFF, "staff"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "suspended"
    assert body["enforcement_reason"] == "reported as fake listing"

    # browse/covers: gone
    assert str(b.id) not in await _covers_ids(http)

    # search: the republished fat event carries a null snapshot -> indexer
    # deletes the doc (delete path covered by test_search_indexing.py)
    business_events = [p for t, p in published if t == "business.updated"]
    assert len(business_events) == 1
    assert business_events[0]["snapshot"] is None
    assert business_events[0]["doc_id"] == f"business_{b.id.hex}"

    # public profile: 410-style unavailable, NOT 404
    detail = await http.get(f"/directory/businesses/{slug}")
    assert detail.status_code == 410
    assert detail.json()["detail"] == "business_unavailable"

    # owner still sees it, with the reason (dashboard notice)
    mine = await http.get("/directory/businesses", headers=_as(OWNER))
    assert mine.status_code == 200
    entry = next(i for i in mine.json()["items"] if i["id"] == str(b.id))
    assert entry["status"] == "suspended"
    assert entry["enforcement_reason"] == "reported as fake listing"

    # owner may still edit while suspended (suspension is not a lockout)
    patch = await http.patch(
        f"/directory/businesses/{b.id}", json={"name": "Renamed Dairy"}, headers=_as(OWNER)
    )
    assert patch.status_code == 200


async def test_suspend_conflicts(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    b = await _business(session)
    first = await http.post(
        f"/admin/directory/businesses/{b.id}/suspend",
        json={"reason": "x"},
        headers=_as(STAFF, "staff"),
    )
    assert first.status_code == 200
    again = await http.post(
        f"/admin/directory/businesses/{b.id}/suspend",
        json={"reason": "x"},
        headers=_as(STAFF, "staff"),
    )
    assert again.status_code == 409
    assert again.json()["detail"] == "already_suspended"

    disabled = await http.post(
        f"/admin/directory/businesses/{b.id}/disable",
        json={"reason": "y"},
        headers=_as(STAFF, "staff"),
    )
    assert disabled.status_code == 200
    resp = await http.post(
        f"/admin/directory/businesses/{b.id}/suspend",
        json={"reason": "z"},
        headers=_as(STAFF, "staff"),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "business_disabled"


async def test_unknown_business_404(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, _ = api
    resp = await http.post(
        f"/admin/directory/businesses/{uuid.uuid4()}/suspend",
        json={"reason": "x"},
        headers=_as(STAFF, "staff"),
    )
    assert resp.status_code == 404


# --- disable (non-negotiable 3, console-lock half) -------------------------


async def test_disable_locks_owner_console(
    api: tuple[httpx.AsyncClient, AsyncSession],
    published: list[tuple[str, dict[str, Any]]],
) -> None:
    http, session = api
    b = await _business(session)
    resp = await http.post(
        f"/admin/directory/businesses/{b.id}/disable",
        json={"reason": "fraud confirmed"},
        headers=_as(STAFF, "staff"),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"

    # owner writes are locked
    patch = await http.patch(
        f"/directory/businesses/{b.id}", json={"name": "Evasive Rename"}, headers=_as(OWNER)
    )
    assert patch.status_code == 403
    assert patch.json()["detail"] == "business_disabled"

    # owner analytics (console read) locked too
    analytics = await http.get(
        f"/directory/businesses/{b.id}/analytics?days=30", headers=_as(OWNER)
    )
    assert analytics.status_code == 403

    # the list still shows it (the console renders the locked card from this)
    mine = await http.get("/directory/businesses", headers=_as(OWNER))
    entry = next(i for i in mine.json()["items"] if i["id"] == str(b.id))
    assert entry["status"] == "disabled"

    # public profile: same 410 as suspended (no state leak)
    detail = await http.get(f"/directory/businesses/{b.slug}")
    assert detail.status_code == 410

    # search removal event fired here too
    business_events = [p for t, p in published if t == "business.updated"]
    assert business_events and business_events[-1]["snapshot"] is None


# --- audit + reinstate (non-negotiable 4) ----------------------------------


async def test_enforcement_audits_and_reinstate_restores_prior_state(
    api: tuple[httpx.AsyncClient, AsyncSession],
    published: list[tuple[str, dict[str, Any]]],
) -> None:
    http, session = api
    b = await _business(session)

    suspend = await http.post(
        f"/admin/directory/businesses/{b.id}/suspend",
        json={"reason": "step one"},
        headers=_as(STAFF, "staff"),
    )
    assert suspend.status_code == 200
    entry = await session.scalar(
        select(AuditEntry).where(AuditEntry.action == "directory.business_suspended")
    )
    assert entry is not None
    assert entry.actor_user_id == STAFF
    assert entry.target_type == "business"
    assert entry.target_id == str(b.id)
    assert entry.meta == {"reason": "step one", "prior_status": "active"}

    disable = await http.post(
        f"/admin/directory/businesses/{b.id}/disable",
        json={"reason": "step two"},
        headers=_as(STAFF, "staff"),
    )
    assert disable.status_code == 200
    entry = await session.scalar(
        select(AuditEntry).where(AuditEntry.action == "directory.business_disabled")
    )
    assert entry is not None
    assert entry.meta["prior_status"] == "suspended"

    # reinstate #1: restores the state the disable found (suspended)
    first = await http.post(
        f"/admin/directory/businesses/{b.id}/reinstate", json={}, headers=_as(STAFF, "staff")
    )
    assert first.status_code == 200
    assert first.json()["status"] == "suspended"

    # reinstate #2: back to active, enforcement state fully cleared
    second = await http.post(
        f"/admin/directory/businesses/{b.id}/reinstate",
        json={"note": "resolved with owner"},
        headers=_as(STAFF, "staff"),
    )
    assert second.status_code == 200
    body = second.json()
    assert body["status"] == "active"
    assert body["enforcement_reason"] is None

    await session.refresh(b)
    assert b.status == "active"
    assert b.enforcement_reason is None
    assert b.enforcement_prior_status is None

    entries = list(
        await session.scalars(
            select(AuditEntry)
            .where(AuditEntry.action == "directory.business_reinstated")
            # entries[-1] means "the second reinstate", so the order has to be
            # asked for: an unordered SELECT may hand back either row first, and
            # CI caught exactly that. Ids are UUIDv7, so id order is time order.
            .order_by(AuditEntry.id)
        )
    )
    assert len(entries) == 2
    assert entries[-1].meta["note"] == "resolved with owner"

    # active again -> the last republished snapshot is live (re-indexed)
    business_events = [p for t, p in published if t == "business.updated"]
    assert business_events[-1]["snapshot"] is not None

    # public profile is back
    detail = await http.get(f"/directory/businesses/{b.slug}")
    assert detail.status_code == 200

    # reinstating an active business conflicts
    third = await http.post(
        f"/admin/directory/businesses/{b.id}/reinstate", json={}, headers=_as(STAFF, "staff")
    )
    assert third.status_code == 409
    assert third.json()["detail"] == "not_enforced"


# --- is_servable seam + campaign auto-pause (non-negotiable 3) -------------


async def test_is_servable_reflects_enforcement(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """The M3 ad-serving contract, written now (spec): serve-time status
    check via shared.lookups.is_servable. Fail closed on unknowns."""
    from shared.lookups import is_servable

    http, session = api
    b = await _business(session)
    assert await is_servable(session, b.id) is True

    await http.post(
        f"/admin/directory/businesses/{b.id}/suspend",
        json={"reason": "x"},
        headers=_as(STAFF, "staff"),
    )
    await session.refresh(b)
    assert await is_servable(session, b.id) is False

    await http.post(
        f"/admin/directory/businesses/{b.id}/disable",
        json={"reason": "y"},
        headers=_as(STAFF, "staff"),
    )
    await session.refresh(b)
    assert await is_servable(session, b.id) is False

    # unknown business: fail closed
    assert await is_servable(session, uuid.uuid4()) is False


async def test_disable_auto_pauses_active_campaigns(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    from datetime import date, timedelta

    from modules.ads.models import Campaign

    http, session = api
    b = await _business(session)
    today = date.today()

    def _campaign(status: str) -> Campaign:
        return Campaign(
            advertiser_business_id=b.id,
            name=f"{status} campaign",
            status=status,
            flight_start=today - timedelta(days=1),
            flight_end=today + timedelta(days=30),
        )

    active, draft, archived = _campaign("active"), _campaign("draft"), _campaign("archived")
    other_business_campaign = Campaign(
        advertiser_business_id=uuid.uuid4(),
        name="unrelated",
        status="active",
        flight_start=today,
        flight_end=today + timedelta(days=7),
    )
    session.add_all([active, draft, archived, other_business_campaign])
    await session.flush()

    resp = await http.post(
        f"/admin/directory/businesses/{b.id}/disable",
        json={"reason": "fraud confirmed"},
        headers=_as(STAFF, "staff"),
    )
    assert resp.status_code == 200

    for campaign in (active, draft, archived, other_business_campaign):
        await session.refresh(campaign)
    assert active.status == "paused"  # auto-paused; no refund logic v1
    assert draft.status == "draft"  # only ACTIVE campaigns pause
    assert archived.status == "archived"
    assert other_business_campaign.status == "active"  # other advertisers untouched

    # the audit row flags the paused campaigns for manual handling
    entry = await session.scalar(
        select(AuditEntry).where(AuditEntry.action == "directory.business_disabled")
    )
    assert entry is not None
    assert entry.meta["campaigns_paused"] == [str(active.id)]


# --- admin lookup + enforcement log ----------------------------------------


async def test_admin_lookup_and_enforcement_log(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    http, session = api
    b = await _business(session)

    await http.post(
        f"/admin/directory/businesses/{b.id}/suspend",
        json={"reason": "first"},
        headers=_as(STAFF, "staff"),
    )
    await http.post(
        f"/admin/directory/businesses/{b.id}/reinstate", json={}, headers=_as(STAFF, "staff")
    )

    lookup = await http.get(f"/admin/directory/businesses/{b.slug}", headers=_as(STAFF, "staff"))
    assert lookup.status_code == 200
    body = lookup.json()
    assert body["id"] == str(b.id)
    assert body["status"] == "active"
    assert body["enforcement_reason"] is None
    assert body["enforcement_prior_status"] is None

    log = await http.get(
        f"/admin/directory/businesses/{b.id}/enforcement-log", headers=_as(STAFF, "staff")
    )
    assert log.status_code == 200
    items = log.json()["items"]
    # newest first
    assert [i["action"] for i in items] == [
        "directory.business_reinstated",
        "directory.business_suspended",
    ]
    assert items[1]["metadata"] == {"reason": "first", "prior_status": "active"}
    assert items[0]["actor_user_id"] == str(STAFF)

    guest = await http.get(f"/admin/directory/businesses/{b.id}/enforcement-log")
    assert guest.status_code == 401
