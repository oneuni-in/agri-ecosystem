"""Admin user management (D11.D). Threat model: admin is a PII-leak surface
and a privilege-escalation surface.

- Users are addressed by agri_id everywhere - internal UUIDs never appear.
- The full phone never renders: search accepts a 4-digit suffix, responses
  carry phone_last4 only (non-negotiable 2, pinned by tests).
- roles.assign gates role changes; touching the super_admin role additionally
  requires the CALLER to hold super_admin (escalation guard).
- Suspend = status flip + revoke_everything in ONE transaction (takes effect
  within one request cycle: the resolver re-checks status on every request)
  + best-effort back-channel to BFFs. Suspend is not delete - no row is
  removed anywhere.
- Audit: real rows in schema `audit` via shared.audit.audit() (D12),
  written call-site-for-call-site where logger.warning placeholders stood.
  Per module rules nothing logs bodies or query strings.
"""

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.backchannel import notify_logout_everywhere
from modules.identity.models import Profile, Role, User, UserRole
from modules.identity.phone import phone_last4
from modules.identity.rbac import require_permission
from modules.identity.schemas import IdentityPublicSchema
from modules.identity.service import UnknownRoleError, assign_role
from modules.identity.session_auth import PrincipalDep
from modules.identity.session_service import WebPrincipal, revoke_everything
from shared.audit import audit
from shared.db import get_session
from shared.events import publish
from shared.pagination import paginate
from shared.security import SecureRouter
from shared.telemetry import get_logger

logger = get_logger(__name__)

EVENT_STREAM = "identity"

admin_router = SecureRouter(prefix="/admin", tags=["admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

SUPER_ADMIN = "super_admin"
_LAST4_RE = re.compile(r"^\d{4}$")


class AdminUserOut(IdentityPublicSchema):
    agri_id: str
    phone_last4: str
    status: str
    name: str | None
    roles: list[str]
    created_at: datetime


class AdminUserPage(BaseModel):
    items: list[AdminUserOut]
    next_cursor: str | None


class AdminUserDetailOut(AdminUserOut):
    state: str | None
    district: str | None
    pincode: str | None
    language: str | None
    interests: list[str]
    has_avatar: bool
    completion_score: int


class StatusOut(BaseModel):
    status: Literal["ok"] = "ok"


async def _roles_by_user(
    session: AsyncSession, user_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    if not user_ids:
        return {}
    rows = await session.execute(
        select(UserRole.user_id, Role.name)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id.in_(user_ids))
        .order_by(Role.name)
    )
    grouped: dict[uuid.UUID, list[str]] = {}
    for user_id, role_name in rows:
        grouped.setdefault(user_id, []).append(role_name)
    return grouped


async def _names_by_user(
    session: AsyncSession, user_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str | None]:
    if not user_ids:
        return {}
    rows = await session.execute(
        select(Profile.user_id, Profile.name).where(Profile.user_id.in_(user_ids))
    )
    return {user_id: name for user_id, name in rows}


async def _target_user(session: AsyncSession, agri_id: str) -> User:
    user = await session.scalar(select(User).where(User.agri_id == agri_id))
    if user is None:
        raise HTTPException(status_code=404, detail="unknown_user")
    return user


async def _audit(
    session: AsyncSession,
    request: Request,
    action: str,
    *,
    actor: WebPrincipal,
    target: User,
    role: str | None = None,
) -> None:
    """D12: real audit rows (schema audit), call-site-for-call-site where
    logger.warning placeholders stood. agri_ids only - never phone/UUID."""
    meta: dict[str, object] = {"actor": actor.agri_id, "target": target.agri_id}
    if role is not None:
        meta["role"] = role
    await audit(
        session,
        action=action,
        actor_user_id=actor.user_id,
        target_type="user",
        target_id=target.agri_id,
        metadata=meta,
        ip=request.client.host if request.client else None,
    )


@admin_router.get("/users", dependencies=[require_permission("users.read")])
async def search_users(
    q: str,
    principal: PrincipalDep,
    session: SessionDep,
    cursor: str | None = None,
    limit: int = 20,
) -> AdminUserPage:
    """4 digits = phone-suffix match (the ONLY way phone is searchable);
    anything else matches agri_id as an escaped prefix."""
    q = q.strip()
    if not 1 <= len(q) <= 64:
        raise HTTPException(status_code=422, detail="bad_query")
    if _LAST4_RE.fullmatch(q):
        condition = User.phone.endswith(q)
    else:
        condition = User.agri_id.istartswith(q, autoescape=True)
    page = await paginate(session, select(User).where(condition), cursor=cursor, limit=limit)
    user_ids = [user.id for user in page.items]
    roles = await _roles_by_user(session, user_ids)
    names = await _names_by_user(session, user_ids)
    return AdminUserPage(
        items=[
            AdminUserOut(
                agri_id=user.agri_id,
                phone_last4=phone_last4(user.phone),
                status=user.status,
                name=names.get(user.id),
                roles=roles.get(user.id, []),
                created_at=user.created_at,
            )
            for user in page.items
        ],
        next_cursor=page.next_cursor,
    )


async def _detail(session: AsyncSession, user: User) -> AdminUserDetailOut:
    profile = await session.scalar(select(Profile).where(Profile.user_id == user.id))
    roles = await _roles_by_user(session, [user.id])
    return AdminUserDetailOut(
        agri_id=user.agri_id,
        phone_last4=phone_last4(user.phone),
        status=user.status,
        name=profile.name if profile else None,
        roles=roles.get(user.id, []),
        created_at=user.created_at,
        state=profile.state if profile else None,
        district=profile.district if profile else None,
        pincode=profile.pincode if profile else None,
        language=profile.language if profile else None,
        interests=list(profile.interests) if profile else [],
        has_avatar=bool(profile is not None and profile.avatar_key),
        completion_score=profile.completion_score if profile else 0,
    )


@admin_router.get("/users/{agri_id}", dependencies=[require_permission("users.read")])
async def get_user(
    agri_id: str, principal: PrincipalDep, session: SessionDep
) -> AdminUserDetailOut:
    return await _detail(session, await _target_user(session, agri_id))


class AdminRolesOut(IdentityPublicSchema):
    agri_id: str
    roles: list[str]


class RoleIn(BaseModel):
    role: str


def _guard_super_admin(role: str, principal: PrincipalDep) -> None:
    """Escalation guard: only super_admins may grant or revoke super_admin,
    regardless of how the caller came by roles.assign."""
    if role == SUPER_ADMIN and SUPER_ADMIN not in principal.roles:
        raise HTTPException(status_code=403, detail="super_admin_required")


async def _roles_out(session: AsyncSession, user: User) -> AdminRolesOut:
    roles = await _roles_by_user(session, [user.id])
    return AdminRolesOut(agri_id=user.agri_id, roles=roles.get(user.id, []))


@admin_router.post("/users/{agri_id}/roles", dependencies=[require_permission("roles.assign")])
async def add_role(
    agri_id: str, body: RoleIn, principal: PrincipalDep, request: Request, session: SessionDep
) -> AdminRolesOut:
    user = await _target_user(session, agri_id)
    _guard_super_admin(body.role, principal)
    try:
        # begin_nested (SAVEPOINT), not a bare session.rollback(): a full
        # rollback expires every object the session has ever loaded, which
        # would poison the rest of this (long-lived, request-shared) session
        # for no reason - the failure here is scoped to one INSERT.
        async with session.begin_nested():
            await assign_role(session, user.id, body.role)
    except UnknownRoleError as exc:
        raise HTTPException(status_code=404, detail="unknown_role") from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="already_assigned") from exc
    await _audit(
        session, request, "admin.role_assigned", actor=principal, target=user, role=body.role
    )
    # commit BEFORE announcing (session_router/profile_router precedent): an
    # event for a rolled-back role change must not exist. After commit, the
    # publish is best-effort. Locale/email enrichment is deliberately skipped
    # for admin-initiated events - in-app only per EVENT_ROUTES.
    await session.commit()
    try:
        await publish(
            EVENT_STREAM,
            "identity.role_changed",
            {
                "user_id": str(user.id),
                "agri_id": user.agri_id,
                "locale": "en",
                "email": None,
                "phone": None,
                "vars": {"role": body.role},
            },
        )
    except Exception as exc:
        logger.warning(
            "identity.event_publish_failed",
            extra={"extra_fields": {"exc_type": type(exc).__name__}},
        )
    return await _roles_out(session, user)


@admin_router.delete(
    "/users/{agri_id}/roles/{role}", dependencies=[require_permission("roles.assign")]
)
async def remove_role(
    agri_id: str, role: str, principal: PrincipalDep, request: Request, session: SessionDep
) -> AdminRolesOut:
    user = await _target_user(session, agri_id)
    _guard_super_admin(role, principal)
    role_id = await session.scalar(select(Role.id).where(Role.name == role))
    if role_id is None:
        raise HTTPException(status_code=404, detail="unknown_role")
    result = await session.execute(
        delete(UserRole)
        .where(UserRole.user_id == user.id, UserRole.role_id == role_id)
        .returning(UserRole.id)
    )
    if result.first() is None:
        raise HTTPException(status_code=404, detail="not_assigned")
    await _audit(session, request, "admin.role_removed", actor=principal, target=user, role=role)
    return await _roles_out(session, user)


async def _guard_suspend_target(session: AsyncSession, user: User, principal: PrincipalDep) -> None:
    if user.id == principal.user_id:
        raise HTTPException(status_code=400, detail="cannot_suspend_self")
    target_roles = (await _roles_by_user(session, [user.id])).get(user.id, [])
    if SUPER_ADMIN in target_roles and SUPER_ADMIN not in principal.roles:
        raise HTTPException(status_code=403, detail="super_admin_required")


@admin_router.post("/users/{agri_id}/suspend", dependencies=[require_permission("users.suspend")])
async def suspend_user(
    agri_id: str, principal: PrincipalDep, request: Request, session: SessionDep
) -> StatusOut:
    user = await _target_user(session, agri_id)
    await _guard_suspend_target(session, user, principal)
    if user.status == "suspended":
        raise HTTPException(status_code=409, detail="already_suspended")
    user.status = "suspended"
    await revoke_everything(session, user.id)
    try:
        await notify_logout_everywhere(session, user.id)
    except Exception as exc:
        # a dead BFF must never roll back the suspension (mirrors D09's
        # logout-everywhere handler; exc message never logged - PII risk)
        logger.warning(
            "backchannel.logout.notify_failed",
            extra={"extra_fields": {"exc_type": type(exc).__name__}},
        )
    await _audit(session, request, "admin.user_suspended", actor=principal, target=user)
    return StatusOut()


@admin_router.post(
    "/users/{agri_id}/reactivate", dependencies=[require_permission("users.suspend")]
)
async def reactivate_user(
    agri_id: str, principal: PrincipalDep, request: Request, session: SessionDep
) -> StatusOut:
    user = await _target_user(session, agri_id)
    if user.status != "suspended":
        raise HTTPException(status_code=409, detail="not_suspended")
    user.status = "active"
    await session.flush()
    await _audit(session, request, "admin.user_reactivated", actor=principal, target=user)
    return StatusOut()
