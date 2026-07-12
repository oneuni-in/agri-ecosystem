"""Own-profile endpoints (D11.A/B): GET/PATCH /identity/profile.

Per module rules nothing here logs bodies or query strings. All routes are
private (SecureRouter default) and additionally permission-gated - profile.*
are two of the three sample permissions the D11 tests pin the pattern on.

Avatar upload (POST /identity/profile/avatar) lands in Task 7 - it needs
shared.storage.put_object/StorageError, which don't exist yet. Nothing here
imports modules.identity.avatar or shared.storage for that reason.
"""

from typing import Annotated, Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import Profile, User
from modules.identity.profile_service import (
    INTERESTS_MAX,
    ProfileUpdateError,
    apply_location,
    get_or_create_profile,
    get_visibility,
    live_score,
    normalize_interests,
    normalize_name,
    recompute_score,
    set_visibility,
)
from modules.identity.rbac import require_permission
from modules.identity.schemas import IdentityPublicSchema
from modules.identity.session_auth import PrincipalDep
from shared.db import get_session
from shared.events import publish
from shared.security import SecureRouter
from shared.telemetry import get_logger

logger = get_logger(__name__)

profile_router = SecureRouter(prefix="/identity/profile", tags=["profile"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

EVENT_STREAM = "identity"


class ProfileOut(IdentityPublicSchema):
    agri_id: str
    name: str | None
    state: str | None
    district: str | None
    pincode: str | None
    language: str | None
    interests: list[str]
    has_avatar: bool
    completion_score: int
    visibility: dict[str, bool]


async def _load_user(session: AsyncSession, principal: PrincipalDep) -> User:
    user = await session.scalar(select(User).where(User.id == principal.user_id))
    assert user is not None  # the resolver proved existence this request
    return user


async def _profile_out(session: AsyncSession, user: User, profile: Profile | None) -> ProfileOut:
    return ProfileOut(
        agri_id=user.agri_id,
        name=profile.name if profile else None,
        state=profile.state if profile else None,
        district=profile.district if profile else None,
        pincode=profile.pincode if profile else None,
        language=profile.language if profile else None,
        interests=list(profile.interests) if profile else [],
        has_avatar=bool(profile is not None and profile.avatar_key),
        completion_score=live_score(user, profile),
        visibility=await get_visibility(session, user.id),
    )


@profile_router.get("", dependencies=[require_permission("profile.read")])
async def get_profile(principal: PrincipalDep, session: SessionDep) -> ProfileOut:
    """Live-computed score: pre-D11 rows (stored score 0) read correctly and
    self-heal on their next write."""
    user = await _load_user(session, principal)
    profile = await session.scalar(select(Profile).where(Profile.user_id == user.id))
    return await _profile_out(session, user, profile)


class ProfilePatchIn(BaseModel):
    """Progressive: only supplied fields change; nothing is cleared in v1.
    extra="forbid" is the free-text-location rejection (state/district are
    derived from pincode, never accepted)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    pincode: str | None = Field(default=None, pattern=r"^\d{6}$")
    language: Literal["en", "ta", "hi"] | None = None
    # min_length=1: an empty list would CLEAR a previously-set field, breaking
    # the progressive-only invariant (scores only rise, crossings fire once).
    interests: list[str] | None = Field(default=None, min_length=1, max_length=INTERESTS_MAX)
    visibility: dict[str, bool] | None = None


async def _commit_and_announce(session: AsyncSession, *, user: User, crossed: bool) -> None:
    """Commit BEFORE announcing: a profile.completed for a rolled-back update
    would hand out D13 coins for a state that never existed (mirrors D07's
    commit-before-respond precedent; expire_on_commit=False keeps the ORM
    objects readable for the response). After the commit the publish is
    best-effort - a Redis blip must not 500 a successful save."""
    await session.commit()
    if not crossed:
        return
    try:
        await publish(
            EVENT_STREAM,
            "profile.completed",
            {"user_id": str(user.id), "agri_id": user.agri_id, "score": 100},
        )
    except Exception as exc:
        logger.warning(
            "profile.completed.publish_failed",
            extra={"extra_fields": {"exc_type": type(exc).__name__}},
        )


@profile_router.patch("", dependencies=[require_permission("profile.write")])
async def patch_profile(
    body: ProfilePatchIn, principal: PrincipalDep, session: SessionDep
) -> ProfileOut:
    user = await _load_user(session, principal)
    profile = await get_or_create_profile(session, user.id)
    try:
        if body.name is not None:
            profile.name = normalize_name(body.name)
        if body.pincode is not None:
            await apply_location(session, profile, body.pincode)
        if body.language is not None:
            profile.language = body.language
        if body.interests is not None:
            profile.interests = normalize_interests(body.interests)
        if body.visibility is not None:
            await set_visibility(session, user.id, body.visibility)
    except ProfileUpdateError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    _, crossed = await recompute_score(session, user=user, profile=profile)
    await _commit_and_announce(session, user=user, crossed=crossed)
    return await _profile_out(session, user, profile)
