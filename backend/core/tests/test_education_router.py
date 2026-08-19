"""education public routes: reachable without auth, and honest about trust.

The client fixture here binds `owner_session` rather than the shared
`d26_helpers.api` fixture's `db_session`. That is not a shortcut around the
grant: education grants app_rt SELECT only (0049), so a fixture on db_session
cannot seed a college to then read back. That app_rt really can SELECT here is
proven separately, in test_education_models.py, through the app's own runtime
URL.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.education.models import Guide, Institution, Programme, StudentResource
from shared.db import get_session
from shared.security import register_principal_resolver


@pytest.fixture
async def api(owner_session: AsyncSession) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield owner_session

    async def _resolver(request: Request, session: AsyncSession) -> object | None:
        return None  # every education route is public; no principal needed

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as client:
        yield client, owner_session


async def _seed(session: AsyncSession, slug: str, **kw: Any) -> Institution:
    row = Institution(
        slug=slug,
        name_en=kw.pop("name_en", "Test College"),
        kind=kw.pop("kind", "affiliated_college"),
        country_code="IN",
        trust=kw.pop("trust", "verified"),
        status=kw.pop("status", "active"),
        source_url="https://example.ac.in/",
        last_verified_at=date(2026, 8, 10),
        **kw,
    )
    session.add(row)
    await session.flush()
    return row


async def test_the_routes_are_public(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    """No session, no 401 -- a college page is SSR'd for anonymous readers."""
    client, _ = api
    for path in (
        "/education/institutions",
        "/education/states",
        "/education/programmes",
        "/education/student-resources",
        "/education/guides",
    ):
        assert (await client.get(path)).status_code == 200, path


def test_public_routes_are_registered() -> None:
    """The second half of the two-place declaration. dump_public_routes.py
    --check fails CI if public_routes.txt disagrees with the live app."""
    app = create_app()
    for path in (
        "/education/institutions",
        "/education/institutions/{slug}",
        "/education/programmes",
        "/education/student-resources",
        "/education/student-resources/{slug}",
        "/education/guides",
        "/education/guides/{slug}",
        "/education/states",
    ):
        assert path in app.state.public_routes, path


def test_no_education_route_accepts_a_write() -> None:
    """app_rt holds SELECT only, so a write route would fail at runtime
    anyway. This asserts none was written -- the failure mode is someone
    copying a router from a module that has one."""
    app = create_app()
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/education"):
            methods: set[str] = getattr(route, "methods", set())
            assert methods <= {"GET", "HEAD", "OPTIONS"}, f"{path} accepts {methods}"


async def test_unknown_slug_is_a_real_404(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, _ = api
    response = await client.get("/education/institutions/no-such-college")
    assert response.status_code == 404
    assert response.json()["detail"] == "institution_not_found"


async def test_a_merged_row_returns_200_and_the_pointer_not_a_redirect(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """The API hands back the pointer; the PAGE issues the 301.

    A 3xx here would be followed silently by fetch, and the caller would
    receive the successor's JSON under the URL it asked for.
    """
    client, session = api
    target = await _seed(session, "new-name-college")
    await _seed(session, "old-name-college", status="merged", merged_into_id=target.id)

    response = await client.get("/education/institutions/old-name-college", follow_redirects=False)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "merged"
    assert body["merged_into_slug"] == "new-name-college"


async def test_a_listed_row_emits_no_admission_data_over_the_wire(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """The serializer gate, asserted end-to-end rather than in-process."""
    client, session = api
    inst = await _seed(session, "bulk-college", trust="listed")
    programme = Programme(
        slug="bsc-ag-bulk",
        name_en="B.Sc. Agriculture",
        level="ug",
        discipline="agriculture",
        duration_months=48,
    )
    session.add(programme)
    await session.flush()
    from modules.education.models import InstitutionProgramme

    session.add(
        InstitutionProgramme(
            institution_id=inst.id,
            programme_id=programme.id,
            intake_seats=120,
            annual_fees_inr=45000,
            admission_route="direct",
            source_url="https://example.ac.in/fees",
            last_verified_at=date(2026, 8, 10),
        )
    )
    await session.flush()

    body = (await client.get("/education/institutions/bulk-college")).json()

    assert body["can_show_admission_data"] is False
    offering = body["programmes"][0]
    assert offering["intake_seats"] is None
    assert offering["annual_fees_inr"] is None
    assert offering["admission_route"] is None
    # The raw numbers must not appear anywhere in the payload either.
    assert "45000" not in (await client.get("/education/institutions/bulk-college")).text


async def test_a_bad_filter_value_is_422_not_an_empty_page(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """An empty 200 tells a caller their filter matched nothing. A wrong enum
    value is a different fact and deserves a different answer."""
    client, _ = api
    response = await client.get("/education/institutions", params={"kind": "hogwarts"})
    assert response.status_code == 422


async def test_a_malformed_cursor_is_422_not_a_500(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, _ = api
    response = await client.get("/education/institutions", params={"cursor": "!!!not-b64!!!"})
    assert response.status_code == 422


async def test_limit_is_bounded(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    """An unbounded limit is a free full-table scan on a public route."""
    client, _ = api
    assert (await client.get("/education/institutions", params={"limit": 500})).status_code == 422


async def test_a_draft_guide_404s_exactly_like_a_missing_one(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    session.add(
        Guide(
            slug="tn-counselling-2026",
            title_en="TN Agri Counselling 2026",
            kind="counselling",
            summary_en="Rounds and dates.",
            steps=[],
            official_links=["https://tnau.ac.in/"],
            last_verified_at=date(2026, 8, 10),
            status="draft",
        )
    )
    await session.flush()

    drafted = await client.get("/education/guides/tn-counselling-2026")
    missing = await client.get("/education/guides/no-such-guide")

    assert drafted.status_code == missing.status_code == 404
    assert drafted.json() == missing.json(), "a draft must be indistinguishable from absent"


async def test_draft_guides_are_absent_from_the_index(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    session.add(
        Guide(
            slug="draft-guide",
            title_en="Draft",
            kind="general",
            summary_en="x",
            steps=[],
            official_links=["https://x.gov.in/"],
            last_verified_at=date(2026, 8, 10),
            status="draft",
        )
    )
    session.add(
        Guide(
            slug="live-guide",
            title_en="Live",
            kind="general",
            summary_en="x",
            steps=[],
            official_links=["https://x.gov.in/"],
            last_verified_at=date(2026, 8, 10),
            status="published",
        )
    )
    await session.flush()

    slugs = [item["slug"] for item in (await client.get("/education/guides")).json()]
    assert "live-guide" in slugs
    assert "draft-guide" not in slugs


async def test_archived_resources_are_absent_from_the_index(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """An expired scholarship listed as live wastes a student's application."""
    client, session = api
    session.add(
        StudentResource(
            slug="dead-scholarship",
            name_en="Old Scheme",
            kind="scholarship",
            scope="india",
            provider="ICAR",
            official_url="https://icar.org.in/",
            last_verified_at=date(2026, 8, 10),
            status="archived",
        )
    )
    session.add(
        StudentResource(
            slug="live-scholarship",
            name_en="Current Scheme",
            kind="scholarship",
            scope="india",
            provider="ICAR",
            official_url="https://icar.org.in/",
            last_verified_at=date(2026, 8, 10),
            status="active",
        )
    )
    await session.flush()

    body = (await client.get("/education/student-resources")).json()
    slugs = [item["slug"] for item in body["items"]]
    assert "live-scholarship" in slugs
    assert "dead-scholarship" not in slugs
    assert (await client.get("/education/student-resources/dead-scholarship")).status_code == 404


async def test_resource_filters_reject_unknown_enum_values(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, _ = api
    assert (
        await client.get("/education/student-resources", params={"kind": "lottery"})
    ).status_code == 422
    assert (await client.get("/education/guides", params={"kind": "rumour"})).status_code == 422


async def test_programmes_serve_the_whole_catalog_uncursored(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """~47 rows, registry-as-data. A cursor here would be ceremony."""
    client, session = api
    session.add(
        Programme(
            slug="bsc-agriculture",
            name_en="B.Sc. (Hons.) Agriculture",
            level="ug",
            discipline="agriculture",
            duration_months=48,
        )
    )
    await session.flush()

    body = (await client.get("/education/programmes")).json()
    assert any(item["slug"] == "bsc-agriculture" for item in body)
    assert isinstance(body, list), "not paginated -- a bounded registry"


async def test_an_id_is_never_accepted_where_a_slug_belongs(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """Path params are slug-shaped by pattern. A UUID contains no uppercase or
    underscores but the guard is worth pinning: these routes must not become a
    second way to address a row."""
    client, _ = api
    response = await client.get(f"/education/institutions/{uuid.uuid4()}")
    assert response.status_code in (404, 422)
