"""Leads API (D18.B). Inquiry submission is guest-capable (public=True +
optional_auth attribution); everything else is owner- or submitter-gated.
Never log payloads - they carry contact intents (PII-dense)."""

import logging
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import leads_service
from modules.directory.leads_models import Inquiry
from modules.directory.leads_schemas import (
    ContactPayloadIn,
    InquiryCreateIn,
    InquiryOut,
    MilkSubscriptionPayloadIn,
)
from shared.db import get_session
from shared.events import publish
from shared.security import SecureRouter, optional_auth

logger = logging.getLogger(__name__)

router = SecureRouter(prefix="/leads", tags=["leads"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]

EVENT_STREAM = "directory"


def _principal_user_id(request: Request) -> uuid.UUID:
    principal = request.state.principal
    user_id = principal.user_id
    assert isinstance(user_id, uuid.UUID)
    return user_id


async def _publish_best_effort(event_type: str, payload: dict[str, object]) -> None:
    try:
        await publish(EVENT_STREAM, event_type, payload)
    except Exception:  # a Redis blip must never fail a lead submission
        logger.warning(
            "leads: event publish failed",
            extra={"extra_fields": {"event_type": event_type}},
        )


def _validate_payload(inquiry_type: str, payload: dict[str, object]) -> dict[str, object]:
    model = ContactPayloadIn if inquiry_type == "contact" else MilkSubscriptionPayloadIn
    try:
        return model.model_validate(payload).model_dump(mode="json")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="invalid_payload") from exc


@router.post("/inquiries", public=True, status_code=201, dependencies=[Depends(optional_auth)])
async def create_inquiry(
    request: Request, body: InquiryCreateIn, session: SessionDep
) -> InquiryOut:
    clean_payload = _validate_payload(body.type, body.payload)
    try:
        routed = await leads_service.route_inquiry(
            session, pincode=body.pincode, category=body.category, business_id=body.business_id
        )
    except leads_service.BusinessNotCoveredError as exc:
        raise HTTPException(status_code=422, detail="business_not_covered") from exc
    except leads_service.NoCoverageError as exc:
        raise HTTPException(status_code=422, detail="no_coverage") from exc

    principal = getattr(request.state, "principal", None)
    inquiry = Inquiry(
        type=body.type,
        from_user_id=principal.user_id if principal is not None else None,
        business_id=routed.id,
        payload=clean_payload,
        pincode=body.pincode,
        category=body.category,
    )
    session.add(inquiry)
    await session.flush()

    out = InquiryOut(
        id=inquiry.id,
        type=inquiry.type,
        business_id=routed.id,
        business_name=routed.name,
        status=inquiry.status,
        pincode=inquiry.pincode,
        category=inquiry.category,
        payload=inquiry.payload,
        created_at=inquiry.created_at,
    )
    event_payload: dict[str, object] | None = None
    if routed.owner_user_id is not None:  # unclaimed inboxes have no one to notify
        event_payload = {
            "user_id": str(routed.owner_user_id),
            "inquiry_id": str(inquiry.id),
            "business_id": str(routed.id),
            "vars": {"business_name": routed.name, "inquiry_type": inquiry.type},
        }
    await session.commit()  # commit BEFORE announcing (repo-wide event ordering rule)
    if event_payload is not None:
        await _publish_best_effort("lead.created", event_payload)
    return out
