"""Identity's own DPDP sections (ID-U1 W4).

Registered into shared.dpdp by main.create_app(), exactly like the lookups
resolvers. Identity is both the orchestrator of the export and one of its
contributors; this file is the contributor half, kept separate so the two
roles do not blur.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.identity.models import Email, Preference, Profile, SessionWeb, User


async def identity_export(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    """Everything identity holds about this person, in full.

    The phone number appears here UNREDACTED, unlike everywhere else in the
    system: admin surfaces see last-4 only (D11 non-negotiable 2), but this
    archive goes to its own subject, and a data-access right that hands
    someone a masked version of their own number is not one.

    Internal UUIDs are absent. They are server-side forever (the schemas.py
    guard exists to make leaking them structurally impossible) and they tell
    the subject nothing about themselves.
    """
    user = await session.get(User, user_id)
    if user is None:
        return {}
    profile = await session.scalar(select(Profile).where(Profile.user_id == user_id))
    emails = (
        await session.scalars(
            select(Email.email, Email.verified_at).where(Email.user_id == user_id)
        )
    ).all()
    preference = await session.scalar(select(Preference).where(Preference.user_id == user_id))
    sessions = (
        await session.scalars(
            select(SessionWeb)
            .where(SessionWeb.user_id == user_id, SessionWeb.revoked_at.is_(None))
            .order_by(SessionWeb.created_at.desc())
        )
    ).all()
    return {
        "handle": user.agri_id,
        "phone": user.phone,
        "phone_verified": user.phone_verified_at is not None,
        "status": user.status,
        "member_since": user.created_at.isoformat(),
        "handle_change_used": user.agri_id_changed_once,
        "profile": None
        if profile is None
        else {
            "name": profile.name,
            "state": profile.state,
            "district": profile.district,
            "pincode": profile.pincode,
            "language": profile.language,
            "interests": list(profile.interests or []),
            "has_photo": profile.avatar_key is not None,
            "completion_score": profile.completion_score,
        },
        "emails": [{"email": e, "verified": v is not None} for e, v in emails],
        "preferences": None
        if preference is None
        else {"notifications": preference.notifications, "privacy": preference.privacy},
        # sessions are the person's own security record - "where am I signed
        # in" is data about them, and it is what /devices renders
        "active_sessions": [
            {
                "device": s.device_kind,
                "label": s.device_label,
                "created_at": s.created_at.isoformat(),
                "last_seen_at": s.last_seen_at.isoformat() if s.last_seen_at else None,
            }
            for s in sessions
        ],
    }
