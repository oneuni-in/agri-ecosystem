"""Notify routes (D12): notification center + channel preferences.

All private (SecureRouter default); the principal comes from require_auth via
request.state.principal - notify never imports identity. Bodies render at
read time in the requested locale (lenient mode: a stale payload must not
500 the inbox)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, StringConstraints, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.models import Notification, Preference, PushSubscription
from modules.notify.push_endpoints import is_allowed_push_endpoint
from modules.notify.rendering import load_template, render_template
from shared.db import get_session
from shared.i18n import SUPPORTED_LOCALES
from shared.pagination import paginate
from shared.security import SecureRouter

router = SecureRouter(prefix="/notify", tags=["notify"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

TOGGLEABLE_CHANNELS = ("sms", "email", "push")


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
    channel: Literal["sms", "email", "push"]
    enabled: bool


_Endpoint = Annotated[str, StringConstraints(min_length=8, max_length=1024)]


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionIn(BaseModel):
    endpoint: _Endpoint
    keys: PushKeys
    ua_label: Annotated[str, StringConstraints(max_length=80)] | None = None

    @field_validator("endpoint")
    @classmethod
    def _known_push_service(cls, value: str) -> str:
        """SSRF gate: the server POSTs to this URL later, so it may only ever
        point at a real push service (modules/notify/push_endpoints.py)."""
        if not is_allowed_push_endpoint(value):
            raise ValueError("unsupported_push_provider")
        return value


class PushUnsubscribeIn(BaseModel):
    endpoint: _Endpoint


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


@router.post("/push/subscriptions")
async def push_subscribe(
    body: PushSubscriptionIn, request: Request, session: SessionDep
) -> StatusOut:
    """Upsert by endpoint: a browser re-subscribing (or a device changing
    hands between accounts) must never 409 - last writer owns the endpoint.
    The endpoint URL is stored for sends, NEVER logged (module rule)."""
    row = await session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )
    if row is None:
        session.add(
            PushSubscription(
                user_id=_user_id(request),
                endpoint=body.endpoint,
                p256dh=body.keys.p256dh,
                auth=body.keys.auth,
                ua_label=body.ua_label,
            )
        )
    else:
        row.user_id = _user_id(request)
        row.p256dh = body.keys.p256dh
        row.auth = body.keys.auth
        row.ua_label = body.ua_label
    return StatusOut()


@router.delete("/push/subscriptions")
async def push_unsubscribe(
    body: PushUnsubscribeIn, request: Request, session: SessionDep
) -> StatusOut:
    row = await session.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint,
            PushSubscription.user_id == _user_id(request),
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="unknown_subscription")
    await session.delete(row)
    return StatusOut()


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
