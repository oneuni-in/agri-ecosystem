"""D12 notify API: owner-scoped list/read/unread/preferences."""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import cast

import httpx
import pytest
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.identity.session_service import WebPrincipal
from modules.notify.models import Delivery, Notification, Preference, Template
from modules.notify.rendering import render_template
from modules.notify.service import NotifyRequest, dispatch
from shared.db import get_session
from shared.security import register_principal_resolver

USER_A = uuid.uuid4()
USER_B = uuid.uuid4()


def _resolver_for(
    user_id: uuid.UUID,
) -> Callable[[Request, AsyncSession], Awaitable[object | None]]:
    async def resolver(request: Request, session: AsyncSession) -> WebPrincipal | None:
        return WebPrincipal(
            user_id=user_id,
            agri_id="AG00000001",
            roles=(),
            session_id=None,
            fingerprint=None,
        )

    return cast(Callable[[Request, AsyncSession], Awaitable[object | None]], resolver)


@pytest.fixture
async def api(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    """Registers a stub principal resolver for USER_A. notify never imports
    identity - the resolver only needs to be WebPrincipal-shaped, no real
    login flow required (contrast test_admin_router.py's full-login setup)."""
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    register_principal_resolver(_resolver_for(USER_A))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://id.test") as client:
        yield client


async def test_list_newest_first_renders_locale_and_excludes_other_users(
    api: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    n1 = Notification(user_id=USER_A, template_key="role_changed", payload={"role": "farmer"})
    n2 = Notification(user_id=USER_A, template_key="role_changed", payload={"role": "staff"})
    other = Notification(user_id=USER_B, template_key="role_changed", payload={"role": "farmer"})
    db_session.add_all([n1, n2, other])
    await db_session.flush()

    response = await api.get("/notify/notifications", params={"locale": "ta"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    # newest first (n2 created after n1)
    assert body["items"][0]["id"] == str(n2.id)
    assert body["items"][1]["id"] == str(n1.id)
    assert all(item["id"] != str(other.id) for item in body["items"])

    ta_template = await db_session.scalar(
        select(Template).where(
            Template.key == "role_changed",
            Template.channel == "in_app",
            Template.locale == "ta",
        )
    )
    assert ta_template is not None
    expected_newest = render_template(ta_template.body, {"role": "staff"}, strict=False)
    expected_oldest = render_template(ta_template.body, {"role": "farmer"}, strict=False)
    assert body["items"][0]["body"] == expected_newest
    assert body["items"][1]["body"] == expected_oldest


async def test_list_bad_locale_is_422(api: httpx.AsyncClient, db_session: AsyncSession) -> None:
    db_session.add(Notification(user_id=USER_A, template_key="role_changed", payload={"role": "x"}))
    await db_session.flush()
    response = await api.get("/notify/notifications", params={"locale": "xx"})
    assert response.status_code == 422


async def test_mark_read_is_idempotent_and_404s_for_foreign_id(
    api: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    mine = Notification(user_id=USER_A, template_key="role_changed", payload={"role": "farmer"})
    theirs = Notification(user_id=USER_B, template_key="role_changed", payload={"role": "farmer"})
    db_session.add_all([mine, theirs])
    await db_session.flush()

    first = await api.post(f"/notify/notifications/{mine.id}/read")
    assert first.status_code == 200
    await db_session.refresh(mine)
    first_read_at = mine.read_at
    assert first_read_at is not None

    second = await api.post(f"/notify/notifications/{mine.id}/read")
    assert second.status_code == 200
    await db_session.refresh(mine)
    assert mine.read_at == first_read_at  # unchanged: no-op, not re-stamped

    foreign = await api.post(f"/notify/notifications/{theirs.id}/read")
    assert foreign.status_code == 404


async def test_read_all_zeroes_unread_count(
    api: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add_all(
        [
            Notification(user_id=USER_A, template_key="role_changed", payload={"role": "a"}),
            Notification(user_id=USER_A, template_key="role_changed", payload={"role": "b"}),
        ]
    )
    await db_session.flush()

    before = await api.get("/notify/unread-count")
    assert before.json()["unread"] == 2

    read_all = await api.post("/notify/notifications/read-all")
    assert read_all.status_code == 200

    after = await api.get("/notify/unread-count")
    assert after.json()["unread"] == 0


async def test_preferences_default_enabled_put_flips_and_dispatch_skips(
    api: httpx.AsyncClient, db_session: AsyncSession, otp_redis: object
) -> None:
    default = await api.get("/notify/preferences")
    assert default.status_code == 200
    items = {row["channel"]: row["enabled"] for row in default.json()["items"]}
    assert items == {"sms": True, "email": True}

    flipped = await api.put("/notify/preferences", json={"channel": "sms", "enabled": False})
    assert flipped.status_code == 200

    updated = await api.get("/notify/preferences")
    items2 = {row["channel"]: row["enabled"] for row in updated.json()["items"]}
    assert items2 == {"sms": False, "email": True}

    row = await db_session.scalar(
        select(Preference).where(Preference.user_id == USER_A, Preference.channel == "sms")
    )
    assert row is not None and row.enabled is False

    request = NotifyRequest(
        user_id=USER_A,
        template_key="login_new_device",
        payload={"device": "Chrome on Android"},
        phone="+919876500001",
        channels=frozenset({"sms"}),
    )
    notification = await dispatch(db_session, request)
    assert notification is not None
    deliveries = (
        await db_session.scalars(
            select(Delivery).where(Delivery.notification_id == notification.id)
        )
    ).all()
    assert deliveries == []  # sms preference off -> dispatch() skips the channel entirely


async def test_put_preference_channel_in_app_is_422(api: httpx.AsyncClient) -> None:
    response = await api.put("/notify/preferences", json={"channel": "in_app", "enabled": False})
    assert response.status_code == 422
