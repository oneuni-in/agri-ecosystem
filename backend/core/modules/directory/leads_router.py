"""Leads API (D18.B). Inquiry submission is guest-capable (public=True +
optional_auth attribution); everything else is owner- or submitter-gated.
Never log payloads - they carry contact intents (PII-dense)."""

import logging
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import leads_service
from modules.directory import service as directory_service
from modules.directory.leads_models import Inquiry, InquiryResponse
from modules.directory.leads_schemas import (
    ContactPayloadIn,
    InboxInquiryOut,
    InboxPageOut,
    InboxStatsOut,
    InquiryCreateIn,
    InquiryOut,
    InquiryStatus,
    InquiryType,
    MilkSubscriptionPayloadIn,
    MyInquiryOut,
    MyInquiryPageOut,
    PincodeInterestCreateIn,
    PincodeInterestOut,
    ResponseCreateIn,
    ResponseOut,
)
from modules.directory.models import Business
from shared.db import get_session
from shared.events import publish
from shared.pagination import InvalidCursorError, paginate
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


def _inbox_out(inquiry: Inquiry) -> InboxInquiryOut:
    return InboxInquiryOut(
        id=inquiry.id,
        type=inquiry.type,
        status=inquiry.status,
        pincode=inquiry.pincode,
        category=inquiry.category,
        payload=inquiry.payload,
        from_user_id=inquiry.from_user_id,
        created_at=inquiry.created_at,
    )


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


@router.get("/inbox")
async def inbox(
    request: Request,
    session: SessionDep,
    business_id: uuid.UUID,
    status: InquiryStatus | None = None,
    type: InquiryType | None = None,
    cursor: str | None = None,
    limit: LimitQuery = 20,
) -> InboxPageOut:
    user_id = _principal_user_id(request)
    try:
        await directory_service.get_owned_business(session, user_id, business_id)
    except directory_service.BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    query = select(Inquiry).where(Inquiry.business_id == business_id)
    if status is not None:
        query = query.where(Inquiry.status == status)
    if type is not None:
        query = query.where(Inquiry.type == type)
    try:
        page = await paginate(session, query, cursor=cursor, limit=limit, descending=True)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return InboxPageOut(items=[_inbox_out(i) for i in page.items], next_cursor=page.next_cursor)


@router.get("/inbox/stats")
async def inbox_statistics(
    request: Request, session: SessionDep, business_id: uuid.UUID
) -> InboxStatsOut:
    user_id = _principal_user_id(request)
    try:
        await directory_service.get_owned_business(session, user_id, business_id)
    except directory_service.BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    total, responded, avg_seconds = await leads_service.inbox_stats(session, business_id)
    return InboxStatsOut(total=total, responded=responded, avg_response_seconds=avg_seconds)


@router.post("/inquiries/{inquiry_id}/responses", status_code=201)
async def respond_to_inquiry(
    request: Request, inquiry_id: uuid.UUID, body: ResponseCreateIn, session: SessionDep
) -> ResponseOut:
    user_id = _principal_user_id(request)
    try:
        inquiry = await leads_service.get_owned_inquiry(session, user_id, inquiry_id)
    except leads_service.InquiryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Inquiry not found") from exc
    if inquiry.status == "closed":
        raise HTTPException(status_code=409, detail="inquiry_closed")
    response = InquiryResponse(inquiry_id=inquiry.id, business_user_id=user_id, body=body.body)
    session.add(response)
    if inquiry.status == "new":
        inquiry.status = "responded"
    await session.flush()
    event_payload: dict[str, object] | None = None
    if inquiry.from_user_id is not None:  # guests have no inbox to notify
        business = await session.get(Business, inquiry.business_id)
        event_payload = {
            "user_id": str(inquiry.from_user_id),
            "inquiry_id": str(inquiry.id),
            "vars": {"business_name": business.name if business else ""},
        }
    out = ResponseOut(
        id=response.id,
        inquiry_id=response.inquiry_id,
        business_user_id=response.business_user_id,
        body=response.body,
        created_at=response.created_at,
    )
    await session.commit()
    if event_payload is not None:
        await _publish_best_effort("lead.responded", event_payload)
    return out


@router.post("/inquiries/{inquiry_id}/close")
async def close_inquiry(
    request: Request, inquiry_id: uuid.UUID, session: SessionDep
) -> InboxInquiryOut:
    user_id = _principal_user_id(request)
    try:
        inquiry = await leads_service.get_owned_inquiry(session, user_id, inquiry_id)
    except leads_service.InquiryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Inquiry not found") from exc
    inquiry.status = "closed"
    await session.flush()
    out = _inbox_out(inquiry)
    await session.commit()
    return out


@router.get("/mine")
async def my_inquiries(
    request: Request, session: SessionDep, cursor: str | None = None, limit: LimitQuery = 20
) -> MyInquiryPageOut:
    user_id = _principal_user_id(request)
    query = select(Inquiry).where(Inquiry.from_user_id == user_id)
    try:
        page = await paginate(session, query, cursor=cursor, limit=limit, descending=True)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    ids = [i.id for i in page.items]
    responses: dict[uuid.UUID, list[InquiryResponse]] = {}
    if ids:
        rows = await session.scalars(
            select(InquiryResponse)
            .where(InquiryResponse.inquiry_id.in_(ids))
            .order_by(InquiryResponse.id)
        )
        for r in rows:
            responses.setdefault(r.inquiry_id, []).append(r)
    return MyInquiryPageOut(
        items=[
            MyInquiryOut(
                id=i.id,
                type=i.type,
                business_id=i.business_id,
                status=i.status,
                payload=i.payload,
                created_at=i.created_at,
                responses=[
                    ResponseOut(
                        id=r.id,
                        inquiry_id=r.inquiry_id,
                        business_user_id=r.business_user_id,
                        body=r.body,
                        created_at=r.created_at,
                    )
                    for r in responses.get(i.id, [])
                ],
            )
            for i in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.post(
    "/pincode-interest",
    public=True,
    status_code=201,
    dependencies=[Depends(optional_auth)],
)
async def create_pincode_interest(
    request: Request, body: PincodeInterestCreateIn, session: SessionDep
) -> PincodeInterestOut:
    principal = getattr(request.state, "principal", None)
    row = await leads_service.record_pincode_interest(
        session,
        pincode=body.pincode,
        contact=body.contact,
        milk_type=body.milk_type,
        from_user_id=principal.user_id if principal is not None else None,
    )
    out = PincodeInterestOut(
        id=row.id, pincode=row.pincode, district=row.district, created_at=row.created_at
    )
    await session.commit()  # commit BEFORE announcing (repo-wide ordering rule)
    await _publish_best_effort(
        "pincode_interest.created",
        {"pincode": row.pincode, "district": row.district, "milk_type": row.milk_type},
    )
    return out
