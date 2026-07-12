"""id.agri.in session endpoints (D09.A/C/D backend).

/auth/login is the module's only new public route (declared in
public_routes.txt); everything else rides require_auth's session cookie.
Per module rules nothing here logs bodies or query strings - login bodies
carry proofs, handle checks ride the query string.

Cookie discipline (non-negotiable 2): agri_sid is httpOnly + Secure +
SameSite=Lax and HOST-ONLY (no Domain attribute) - the session exists on
id.agri.in and nowhere else. Fixation: login always mints a fresh sid.
"""

import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.backchannel import notify_logout_everywhere
from modules.identity.handles import HandleError, can_change_handle, validate_handle
from modules.identity.models import (
    HandleHistory,
    OAuthClient,
    Profile,
    SessionRefresh,
    SessionWeb,
    User,
)
from modules.identity.otp_service import consume_otp_proof
from modules.identity.refresh_service import revoke_families_for_device, revoke_family
from modules.identity.schemas import IdentityPublicSchema
from modules.identity.service import assign_role, create_user, get_by_phone
from modules.identity.session_auth import PrincipalDep
from modules.identity.session_limits import (
    DEVICE_LABEL_MAX_CHARS,
    SESSION_COOKIE_NAME,
    WEB_SESSION_TTL_SECONDS,
)
from modules.identity.session_service import (
    create_web_session,
    device_fingerprint,
    revoke_everything,
    revoke_web_session,
)
from shared.db import get_session
from shared.pagination import Page, paginate
from shared.security import SecureRouter
from shared.telemetry import get_logger

logger = get_logger(__name__)

session_router = SecureRouter(prefix="/auth", tags=["auth-session"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

AG_FALLBACK_PREFIX = "AG-"


def _fingerprint(request: Request) -> str:
    return device_fingerprint(
        request.headers.get("user-agent"), request.headers.get("sec-ch-ua-platform")
    )


def _set_session_cookie(response: Response, sid: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        sid,
        max_age=WEB_SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
        # no domain= on purpose: host-only, id.agri.in and nowhere else
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", httponly=True, secure=True)


async def _language_for(session: AsyncSession, user_id: uuid.UUID) -> str:
    profile = await session.scalar(select(Profile).where(Profile.user_id == user_id))
    language = profile.language if profile is not None else None
    return language or "en"


class LoginIn(BaseModel):
    otp_proof: str
    device_label: str | None = Field(default=None, max_length=DEVICE_LABEL_MAX_CHARS)


class LoginOut(IdentityPublicSchema):
    status: Literal["ok"] = "ok"
    is_new_user: bool
    agri_id: str
    handle_is_fallback: bool
    language: str


@session_router.post("/login", public=True)
async def login(
    body: LoginIn, request: Request, response: Response, session: SessionDep
) -> LoginOut:
    """OTP-proof -> id.agri.in session. New phones become accounts here."""
    redeemed = await consume_otp_proof(body.otp_proof)
    if redeemed is None or redeemed[1] != "login":
        raise HTTPException(status_code=400, detail="invalid_or_expired_proof")
    phone = redeemed[0]
    user = await get_by_phone(session, phone)
    is_new_user = user is None
    if user is None:
        user = await create_user(session, phone)
        await assign_role(session, user.id, "user")
        user.phone_verified_at = datetime.now(UTC)
        await session.flush()
    if user.status != "active":
        # the proof is already burned (GETDEL) - nothing to roll back
        raise HTTPException(status_code=403, detail="account_unavailable")
    sid = await create_web_session(
        session,
        user_id=user.id,
        fingerprint=_fingerprint(request),
        ip=request.client.host if request.client else None,
        device_label=body.device_label,
    )
    _set_session_cookie(response, sid)
    return LoginOut(
        is_new_user=is_new_user,
        agri_id=user.agri_id,
        handle_is_fallback=user.agri_id.startswith(AG_FALLBACK_PREFIX)
        and not user.agri_id_changed_once,
        language=await _language_for(session, user.id),
    )


class StatusOut(BaseModel):
    status: Literal["ok"] = "ok"


@session_router.post("/logout")
async def logout(
    principal: PrincipalDep, request: Request, response: Response, session: SessionDep
) -> StatusOut:
    """This device only: web session + refresh families minted from it."""
    await revoke_web_session(session, session_id=principal.session_id, user_id=principal.user_id)
    if principal.fingerprint:
        await revoke_families_for_device(
            session, user_id=principal.user_id, fingerprint=principal.fingerprint
        )
    _clear_session_cookie(response)
    return StatusOut()


@session_router.post("/logout-everywhere")
async def logout_everywhere(
    principal: PrincipalDep, response: Response, session: SessionDep
) -> StatusOut:
    """Every session + every refresh family, one request cycle (D09
    non-negotiable 3); then best-effort back-channel to every BFF (D10.D).

    Best-effort is absolute: get_session commits only if this handler returns
    without raising, so ANY exception out of notify_logout_everywhere -
    including one that happens before its own internal gather() shield, e.g.
    a client-registry SELECT or JWT signing failure - would roll back
    revoke_everything above. A dead or misbehaving BFF must never undo the
    user's logout, so nothing from notify is allowed to escape this call."""
    await revoke_everything(session, principal.user_id)
    try:
        await notify_logout_everywhere(session, principal.user_id)
    except Exception as exc:
        # event name + exception type only - the exception message/args are
        # never logged (see module docstring: PII/token material could ride
        # inside them) and exc_info is avoided too: PiiScrubFilter only
        # scrubs record.msg/args, not formatted tracebacks, so exc_info=True
        # would leak whatever a client-registry SELECT or JWT signing
        # failure put in its str().
        logger.warning(
            "backchannel.logout.notify_failed",
            extra={"extra_fields": {"exc_type": type(exc).__name__}},
        )
    _clear_session_cookie(response)
    return StatusOut()


class MeOut(IdentityPublicSchema):
    agri_id: str
    handle_is_fallback: bool
    can_change_handle: bool
    language: str


@session_router.get("/me")
async def me(principal: PrincipalDep, session: SessionDep) -> MeOut:
    user = await session.scalar(select(User).where(User.id == principal.user_id))
    assert user is not None  # resolve_web_session proved existence this request
    return MeOut(
        agri_id=user.agri_id,
        handle_is_fallback=user.agri_id.startswith(AG_FALLBACK_PREFIX)
        and not user.agri_id_changed_once,
        can_change_handle=can_change_handle(user.agri_id_changed_once),
        language=await _language_for(session, user.id),
    )


class HandleIn(BaseModel):
    handle: str


class HandleOut(IdentityPublicSchema):
    agri_id: str


@session_router.post("/handle")
async def set_handle(body: HandleIn, principal: PrincipalDep, session: SessionDep) -> HandleOut:
    """The one free change (D06.B). Signup's pick from the AG- fallback IS the
    change - the flag model has no second dimension, deliberately."""
    try:
        handle = validate_handle(body.handle)
    except HandleError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    user = await session.scalar(select(User).where(User.id == principal.user_id))
    assert user is not None
    if not can_change_handle(user.agri_id_changed_once):
        raise HTTPException(status_code=409, detail="already_changed")
    old = user.agri_id
    user.agri_id = handle
    user.agri_id_changed_once = True
    session.add(HandleHistory(user_id=user.id, old_agri_id=old, new_agri_id=handle))
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="taken") from exc
    return HandleOut(agri_id=handle)


class HandleCheckOut(BaseModel):
    ok: bool
    code: str | None = None


@session_router.get("/handle/check")
async def check_handle(h: str, principal: PrincipalDep, session: SessionDep) -> HandleCheckOut:
    try:
        handle = validate_handle(h)
    except HandleError as exc:
        return HandleCheckOut(ok=False, code=exc.code)
    existing = await session.scalar(select(User.agri_id).where(User.agri_id == handle))
    if existing is not None:
        return HandleCheckOut(ok=False, code="taken")
    return HandleCheckOut(ok=True)


class HandleSuggestOut(BaseModel):
    suggestions: list[str]


_ADJECTIVES = ("green", "sunny", "golden", "fresh", "happy", "bright", "calm", "brave")
_NOUNS = ("farmer", "harvest", "fields", "valley", "sprout", "garden", "grove", "meadow")


@session_router.get("/handle/suggest")
async def suggest_handles(principal: PrincipalDep, session: SessionDep) -> HandleSuggestOut:
    """Wordlist combos, availability-checked in one query. Nothing personal
    goes into a suggestion (no phone digits, no name)."""
    candidates: list[str] = []
    while len(candidates) < 12:
        name = f"{secrets.choice(_ADJECTIVES)}_{secrets.choice(_NOUNS)}{secrets.randbelow(90) + 10}"
        if name not in candidates:
            candidates.append(name)
    taken = set(await session.scalars(select(User.agri_id).where(User.agri_id.in_(candidates))))
    available = [name for name in candidates if name not in taken]
    return HandleSuggestOut(suggestions=available[:3])


class LanguageIn(BaseModel):
    language: Literal["en", "ta", "hi"]


@session_router.post("/language")
async def set_language(body: LanguageIn, principal: PrincipalDep, session: SessionDep) -> StatusOut:
    profile = await session.scalar(select(Profile).where(Profile.user_id == principal.user_id))
    if profile is None:
        session.add(Profile(user_id=principal.user_id, language=body.language))
    else:
        profile.language = body.language
    await session.flush()
    return StatusOut()


class DeviceOut(IdentityPublicSchema):
    device_id: str  # stringified row id of sessions_web / sessions_refresh ROOT
    kind: str  # "web" or the oauth client_id ("web-agri", ...)
    label: str | None
    current: bool
    created_at: datetime
    last_seen_at: datetime | None


class DevicesOut(BaseModel):
    items: list[DeviceOut]
    next_cursor: str | None


@session_router.get("/devices")
async def list_devices(
    principal: PrincipalDep,
    session: SessionDep,
    cursor: str | None = None,
    limit: int = 20,
) -> DevicesOut:
    """Active web sessions, keyset-paginated. App refresh families (bounded:
    <= clients x devices) ride the FIRST page after the web rows - a device
    whose web session is gone still shows its app tokens for revocation."""
    now = datetime.now(UTC)
    page: Page[SessionWeb] = await paginate(
        session,
        select(SessionWeb).where(
            SessionWeb.user_id == principal.user_id,
            SessionWeb.revoked_at.is_(None),
            SessionWeb.expires_at > now,
        ),
        cursor=cursor,
        limit=limit,
    )
    items = [
        DeviceOut(
            device_id=str(row.id),
            kind="web",
            label=row.device_label,
            current=row.id == principal.session_id,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
        )
        for row in page.items
    ]
    if cursor is None:
        family_rows = (
            await session.execute(
                select(SessionRefresh, OAuthClient.client_id)
                .join(OAuthClient, OAuthClient.id == SessionRefresh.client_id)
                .where(
                    SessionRefresh.user_id == principal.user_id,
                    SessionRefresh.revoked_at.is_(None),
                    SessionRefresh.expires_at > now,
                )
                .order_by(SessionRefresh.id)
            )
        ).all()
        items.extend(
            DeviceOut(
                device_id=str(refresh.id),
                kind=client_id,
                label=refresh.device_label,
                current=False,
                created_at=refresh.created_at,
                last_seen_at=refresh.last_used_at,
            )
            for refresh, client_id in family_rows
        )
    return DevicesOut(items=items, next_cursor=page.next_cursor)


class DeviceActionIn(BaseModel):
    device_id: str
    kind: str


def _parse_device_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="unknown_device") from exc


@session_router.post("/devices/revoke")
async def revoke_device(
    body: DeviceActionIn, principal: PrincipalDep, response: Response, session: SessionDep
) -> StatusOut:
    row_id = _parse_device_id(body.device_id)
    if body.kind == "web":
        target = await session.scalar(
            select(SessionWeb).where(
                SessionWeb.id == row_id, SessionWeb.user_id == principal.user_id
            )
        )
        if target is None:
            raise HTTPException(status_code=404, detail="unknown_device")
        await revoke_web_session(session, session_id=row_id, user_id=principal.user_id)
        if target.device_fingerprint:
            await revoke_families_for_device(
                session, user_id=principal.user_id, fingerprint=target.device_fingerprint
            )
        if row_id == principal.session_id:
            _clear_session_cookie(response)  # self-revoke == logout
        return StatusOut()
    refresh = await session.scalar(
        select(SessionRefresh).where(
            SessionRefresh.id == row_id, SessionRefresh.user_id == principal.user_id
        )
    )
    if refresh is None:
        raise HTTPException(status_code=404, detail="unknown_device")
    await revoke_family(session, refresh.family_id)
    return StatusOut()


class DeviceLabelIn(DeviceActionIn):
    label: str = Field(min_length=1, max_length=DEVICE_LABEL_MAX_CHARS)


@session_router.post("/devices/label")
async def label_device(
    body: DeviceLabelIn, principal: PrincipalDep, session: SessionDep
) -> StatusOut:
    row_id = _parse_device_id(body.device_id)
    if body.kind == "web":
        web_row = await session.scalar(
            select(SessionWeb).where(
                SessionWeb.id == row_id, SessionWeb.user_id == principal.user_id
            )
        )
        if web_row is None:
            raise HTTPException(status_code=404, detail="unknown_device")
        web_row.device_label = body.label
    else:
        refresh_row = await session.scalar(
            select(SessionRefresh).where(
                SessionRefresh.id == row_id, SessionRefresh.user_id == principal.user_id
            )
        )
        if refresh_row is None:
            raise HTTPException(status_code=404, detail="unknown_device")
        refresh_row.device_label = body.label
    await session.flush()
    return StatusOut()
