"""Notify routes (D12): notification center + channel preferences.

All private (SecureRouter default); the principal comes from require_auth via
request.state.principal - notify never imports identity. Bodies render at
read time in the requested locale (lenient mode: a stale payload must not
500 the inbox)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.models import Notification, Preference
from modules.notify.rendering import load_template, render_template
from shared.db import get_session
from shared.i18n import SUPPORTED_LOCALES
from shared.pagination import paginate
from shared.security import SecureRouter

router = SecureRouter(prefix="/notify", tags=["notify"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

TOGGLEABLE_CHANNELS = ("sms", "email")


def _user_id(request: Request) -> uuid.UUID:
    principal = getattr(request.state, "principal", None)
    assert principal is not None  # require_auth ran (private route)
    return principal.user_id  # type: ignore[no-any-return]


class NotificationOut(BaseModel):
    id: uuid.UUID
    body: str
    created_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    next_cursor: str | None


class UnreadOut(BaseModel):
    unread: int


class StatusOut(BaseModel):
    status: Literal["ok"] = "ok"


class PreferenceOut(BaseModel):
    channel: str
    enabled: bool


class PreferencesOut(BaseModel):
    items: list[PreferenceOut]


class PreferenceIn(BaseModel):
    channel: Literal["sms", "email"]
    enabled: bool


@router.get("/notifications")
async def list_notifications(
    request: Request,
    session: SessionDep,
    cursor: str | None = None,
    limit: int = 20,
    locale: Annotated[str, Query(pattern="^(en|ta|hi)$")] = "en",
) -> NotificationPage:
    assert locale in SUPPORTED_LOCALES
    page = await paginate(
        session,
        select(Notification).where(Notification.user_id == _user_id(request)),
        cursor=cursor,
        limit=limit,
        descending=True,
    )
    items: list[NotificationOut] = []
    for row in page.items:
        template = await load_template(
            session, key=row.template_key, channel="in_app", locale=locale
        )
        body = (
            render_template(template.body, row.payload, strict=False)
            if template is not None
            else row.template_key
        )
        items.append(
            NotificationOut(id=row.id, body=body, created_at=row.created_at, read_at=row.read_at)
        )
    return NotificationPage(items=items, next_cursor=page.next_cursor)


@router.post("/notifications/read-all")
async def read_all(request: Request, session: SessionDep) -> StatusOut:
    await session.execute(
        update(Notification)
        .where(Notification.user_id == _user_id(request), Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    return StatusOut()


@router.post("/notifications/{notification_id}/read")
async def mark_read(notification_id: uuid.UUID, request: Request, session: SessionDep) -> StatusOut:
    row = await session.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == _user_id(request)
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="unknown_notification")
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        await session.flush()
    return StatusOut()


@router.get("/unread-count")
async def unread_count(request: Request, session: SessionDep) -> UnreadOut:
    count = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == _user_id(request), Notification.read_at.is_(None))
    )
    return UnreadOut(unread=int(count or 0))


@router.get("/preferences")
async def get_preferences(request: Request, session: SessionDep) -> PreferencesOut:
    rows = (
        await session.scalars(select(Preference).where(Preference.user_id == _user_id(request)))
    ).all()
    stored = {row.channel: row.enabled for row in rows}
    return PreferencesOut(
        items=[
            PreferenceOut(channel=channel, enabled=stored.get(channel, True))
            for channel in TOGGLEABLE_CHANNELS
        ]
    )


@router.put("/preferences")
async def put_preference(body: PreferenceIn, request: Request, session: SessionDep) -> StatusOut:
    user_id = _user_id(request)
    row = await session.scalar(
        select(Preference).where(Preference.user_id == user_id, Preference.channel == body.channel)
    )
    if row is None:
        session.add(Preference(user_id=user_id, channel=body.channel, enabled=body.enabled))
    else:
        row.enabled = body.enabled
    return StatusOut()
