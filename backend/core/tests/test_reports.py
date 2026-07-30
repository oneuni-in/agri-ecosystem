"""Business reports (M1.5.A): login-gated POST into the unified moderation
queue. Non-negotiable 1: a report lands in the ops queue and is invisible on
every public surface. Principal injection mirrors test_reviews_router.py
(x-test-user header resolver); ops decisions use the x-test-roles convention
from test_ops_moderation_router.py."""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.directory import reports_service, service
from modules.directory.models import Business, BusinessCoverage, Report
from shared.db import get_session
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

OWNER = uuid.uuid4()
REPORTER = uuid.uuid4()


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
def no_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass the Redis daily cap in tests that aren't about the cap."""

    async def _allow(user_id: uuid.UUID, *, now: datetime) -> None:
        return None

    monkeypatch.setattr(reports_service, "claim_report_slot", _allow)


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


async def _business(session: AsyncSession, *, name: str = "Milk Vendor") -> Business:
    business = await service.create_business(
        session, owner_user_id=OWNER, name=name, type_="vendor", primary_pincode="641001"
    )
    session.add(BusinessCoverage(business_id=business.id, pincode="641001"))
    await session.flush()
    return business


def _report_body(reason: str = "fake_listing", detail: str | None = None) -> dict[str, object]:
    body: dict[str, object] = {"reason": reason}
    if detail is not None:
        body["detail"] = detail
    return body


async def test_report_requires_auth(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    http, session = api
    b = await _business(session)
    resp = await http.post(f"/directory/businesses/{b.slug}/report", json=_report_body())
    assert resp.status_code == 401


async def test_report_lands_pending(
    api: tuple[httpx.AsyncClient, AsyncSession], no_cap: None
) -> None:
    http, session = api
    b = await _business(session)
    resp = await http.post(
        f"/directory/businesses/{b.slug}/report",
        json=_report_body("wrong_info", "Address is years out of date"),
        headers=_as(REPORTER),
    )
    assert resp.status_code == 201
    assert resp.json() == {"status": "pending"}
    row = await session.scalar(select(Report).where(Report.business_id == b.id))
    assert row is not None
    assert row.moderation_status == "pending"
    assert row.reporter_user_id == REPORTER
    assert row.reason == "wrong_info"
    assert row.detail == "Address is years out of date"


async def test_one_pending_report_per_user_per_business(
    api: tuple[httpx.AsyncClient, AsyncSession], no_cap: None
) -> None:
    http, session = api
    b = await _business(session)
    first = await http.post(
        f"/directory/businesses/{b.slug}/report", json=_report_body(), headers=_as(REPORTER)
    )
    assert first.status_code == 201
    second = await http.post(
        f"/directory/businesses/{b.slug}/report", json=_report_body(), headers=_as(REPORTER)
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "report_exists"
    # a different user may still report the same business
    third = await http.post(
        f"/directory/businesses/{b.slug}/report", json=_report_body(), headers=_as(uuid.uuid4())
    )
    assert third.status_code == 201


async def test_other_reason_requires_detail(
    api: tuple[httpx.AsyncClient, AsyncSession], no_cap: None
) -> None:
    http, session = api
    b = await _business(session)
    missing = await http.post(
        f"/directory/businesses/{b.slug}/report", json=_report_body("other"), headers=_as(REPORTER)
    )
    assert missing.status_code == 422
    given = await http.post(
        f"/directory/businesses/{b.slug}/report",
        json=_report_body("other", "Sells unrelated goods"),
        headers=_as(REPORTER),
    )
    assert given.status_code == 201


async def test_report_cap_429(
    api: tuple[httpx.AsyncClient, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    http, session = api
    b = await _business(session)

    async def _deny(user_id: uuid.UUID, *, now: datetime) -> None:
        raise reports_service.ReportCapExceededError()

    monkeypatch.setattr(reports_service, "claim_report_slot", _deny)
    resp = await http.post(
        f"/directory/businesses/{b.slug}/report", json=_report_body(), headers=_as(REPORTER)
    )
    assert resp.status_code == 429
    assert resp.json()["detail"] == "report_cap_exceeded"


async def test_report_cap_unavailable_503(
    api: tuple[httpx.AsyncClient, AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    http, session = api
    b = await _business(session)

    async def _down(user_id: uuid.UUID, *, now: datetime) -> None:
        raise reports_service.ReportsUnavailableError()

    monkeypatch.setattr(reports_service, "claim_report_slot", _down)
    resp = await http.post(
        f"/directory/businesses/{b.slug}/report", json=_report_body(), headers=_as(REPORTER)
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "report_unavailable"


async def test_report_unknown_reason_422(
    api: tuple[httpx.AsyncClient, AsyncSession], no_cap: None
) -> None:
    http, session = api
    b = await _business(session)
    resp = await http.post(
        f"/directory/businesses/{b.slug}/report",
        json=_report_body("i-just-dont-like-it"),
        headers=_as(REPORTER),
    )
    assert resp.status_code == 422


async def test_report_suspended_business_404(
    api: tuple[httpx.AsyncClient, AsyncSession], no_cap: None
) -> None:
    http, session = api
    b = await _business(session)
    b.status = "suspended"
    await session.flush()
    resp = await http.post(
        f"/directory/businesses/{b.slug}/report", json=_report_body(), headers=_as(REPORTER)
    )
    assert resp.status_code == 404


async def test_reports_invisible_on_public_surfaces(
    api: tuple[httpx.AsyncClient, AsyncSession], no_cap: None, tn_geo_sample: None
) -> None:
    """Non-negotiable 1: nothing report-shaped leaks from any public read."""
    http, session = api
    b = await _business(session)
    created = await http.post(
        f"/directory/businesses/{b.slug}/report",
        json=_report_body("fraud_scam", "Took advance payment and vanished"),
        headers=_as(REPORTER),
    )
    assert created.status_code == 201

    detail = await http.get(f"/directory/businesses/{b.slug}")
    assert detail.status_code == 200
    detail_text = detail.text.lower()
    assert "report" not in detail_text
    assert str(REPORTER) not in detail_text
    assert "fraud" not in detail_text

    covers = await http.get("/directory/covers/641001")
    assert covers.status_code == 200
    covers_text = covers.text.lower()
    assert "report" not in covers_text
    assert str(REPORTER) not in covers_text
