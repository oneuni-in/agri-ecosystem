"""Own-profile endpoints (D11.A/B): GET/PATCH /identity/profile.

Per module rules nothing here logs bodies or query strings. All routes are
private (SecureRouter default) and additionally permission-gated - profile.*
are two of the three sample permissions the D11 tests pin the pattern on.

Avatar upload (POST /identity/profile/avatar) - multipart image upload,
type sniffed from magic bytes only, stored via shared.storage.put_object.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.avatar import (
    AVATAR_CONTENT_TYPES,
    MAX_AVATAR_BYTES,
    AvatarError,
    avatar_object_key,
    validate_avatar,
)
from modules.identity.models import FarmProfile, Profile, User
from modules.identity.profile_service import (
    INTERESTS_MAX,
    ProfileUpdateError,
    apply_farm_profile,
    apply_location,
    get_farm_profile,
    get_or_create_profile,
    get_visibility,
    live_missing,
    live_score,
    normalize_describes,
    normalize_interests,
    normalize_name,
    recompute_score,
    set_visibility,
)
from modules.identity.rbac import require_permission
from modules.identity.schemas import IdentityPublicSchema
from modules.identity.session_auth import PrincipalDep
from shared import storage
from shared.db import get_session
from shared.events import publish
from shared.lookups import resolve_owned_businesses
from shared.security import SecureRouter
from shared.telemetry import get_logger

logger = get_logger(__name__)

profile_router = SecureRouter(prefix="/identity/profile", tags=["profile"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

EVENT_STREAM = "identity"


class FarmOut(IdentityPublicSchema):
    """The farm, as its owner sees it. Every field nullable: this section is
    answered in any order or not at all, and a 0 would claim "no animals"
    where the truth is "not said".

    land_area is a STRING on the wire. It is Numeric in the database
    because scheme thresholds are compared per hectare, and serialising a
    Decimal through JSON's float would reintroduce exactly the rounding the
    column type exists to avoid (the D24 Decimal-wire-string precedent).
    """

    land_area: str | None
    land_unit: str | None
    tenure: str | None
    cattle: int | None
    goats: int | None
    poultry: int | None
    irrigation: str | None


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
    # ID-U1 P7: the bar showed a percentage but never what was still empty, so
    # "78%" was a number with no next action. Server-side because it and the
    # score are two renderings of ONE reading of the profile (completion.py's
    # WEIGHTS); deriving this in the client would let them drift apart the
    # moment a weight moves.
    missing: list[str]
    # ID-U1 W5. `describes` is self-description, never authorisation - it
    # decides which section of the page you see, and nothing else.
    describes: list[str]
    # W5's business half collects NOTHING about a shop - the directory listing
    # owns that. This is only so the section can say "you already have one"
    # instead of inviting someone to claim what they already own. Read through
    # the shared.lookups seam; identity cannot touch directory's tables.
    owned_businesses: list[str]
    # None until a farmer answers something. Absent and all-empty are the
    # same thing to the reader, but the null keeps that explicit.
    farm: FarmOut | None
    visibility: dict[str, bool]
    # M1.5.D: "Member since {month year}" - the account's created_at is not
    # PII (no phone, no UUID; the schema guard enforces that at import time)
    member_since: datetime


async def _load_user(session: AsyncSession, principal: PrincipalDep) -> User:
    user = await session.scalar(select(User).where(User.id == principal.user_id))
    assert user is not None  # the resolver proved existence this request
    return user


def _farm_out(row: FarmProfile | None) -> FarmOut | None:
    if row is None:
        return None
    return FarmOut(
        land_area=None if row.land_area is None else format(row.land_area, "f"),
        land_unit=row.land_unit,
        tenure=row.tenure,
        cattle=row.cattle,
        goats=row.goats,
        poultry=row.poultry,
        irrigation=row.irrigation,
    )


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
        missing=live_missing(user, profile),
        describes=list(profile.describes) if profile else [],
        owned_businesses=[b.name for b in await resolve_owned_businesses(session, user.id)],
        farm=_farm_out(await get_farm_profile(session, user.id)),
        visibility=await get_visibility(session, user.id),
        member_since=user.created_at,
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
    describes: list[str] | None = None
    # A DICT rather than a model, because farm fields are individually
    # CLEARABLE and pydantic cannot distinguish an omitted field from an
    # explicit null on a nested model without extra machinery. The keys
    # present in this dict are exactly the fields the caller means to set;
    # the service validates each one.
    farm: dict[str, Any] | None = None


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
        if body.describes is not None:
            profile.describes = normalize_describes(body.describes)
        if body.farm is not None:
            await apply_farm_profile(session, user.id, body.farm)
    except ProfileUpdateError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    _, crossed = await recompute_score(session, user=user, profile=profile)
    await _commit_and_announce(session, user=user, crossed=crossed)
    return await _profile_out(session, user, profile)


@profile_router.get("/avatar", dependencies=[require_permission("profile.read")])
async def get_avatar(principal: PrincipalDep, session: SessionDep) -> Response:
    """The owner's own profile photo, streamed through the API.

    ID-U1 P7: /account showed a bare "✓" where a photo should be, because
    ProfileOut carried has_avatar and no way to actually see the image.

    Deliberately NOT a media-domain URL. Catalog images take that route
    (`media_url` + ensure_prefix_public_read), but a product photo is meant to
    be public and a face is not: avatars have their own visibility toggle on
    this very page, and publishing them to a public-read prefix would leave
    that switch governing whether the URL is SHOWN rather than whether the
    image can be fetched. Owner-scoped and permission-gated keeps the toggle
    meaning what it says. The `avatars/` prefix stays private.
    """
    user = await _load_user(session, principal)
    profile = await session.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile is None or not profile.avatar_key:
        raise HTTPException(status_code=404, detail="no_avatar")
    try:
        data = await storage.get_object(profile.avatar_key)
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail="storage_unavailable") from exc
    content_type = AVATAR_CONTENT_TYPES.get(profile.avatar_key.rsplit(".", 1)[-1], "image/jpeg")
    # private: this is one person's face, and no shared cache may hold it.
    return Response(
        content=data,
        media_type=content_type,
        headers={"cache-control": "private, max-age=0, must-revalidate"},
    )


@profile_router.post("/avatar", dependencies=[require_permission("profile.write")])
async def upload_avatar(
    file: UploadFile, principal: PrincipalDep, session: SessionDep
) -> ProfileOut:
    """Multipart image upload. Type comes from magic bytes only - the part's
    Content-Type header is never consulted."""
    data = await file.read(MAX_AVATAR_BYTES + 1)
    try:
        content_type, ext = validate_avatar(data)
    except AvatarError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    key = avatar_object_key(ext)
    try:
        await storage.put_object(key, data, content_type)
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail="storage_unavailable") from exc
    user = await _load_user(session, principal)
    profile = await get_or_create_profile(session, user.id)
    profile.avatar_key = key
    _, crossed = await recompute_score(session, user=user, profile=profile)
    await _commit_and_announce(session, user=user, crossed=crossed)
    return await _profile_out(session, user, profile)
