"""Post-my-need API (D25). All routes are authed - the guest path is
"OTP login first" (progressive account, D07/D11), so every poster is
phone-verified by construction. Never log payloads (PII-dense)."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import uuid6
from fastapi import Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import activity, leads_service, needs_service
from modules.directory.leads_models import Inquiry, InquiryResponse, Need
from modules.directory.leads_schemas import ResponseOut
from modules.directory.models import Business
from modules.directory.needs_schemas import (
    FulfillIn,
    MyNeedOut,
    MyNeedPageOut,
    NeedCreateIn,
    NeedOut,
    NeedPayloadIn,
    NeedRouteOut,
)
from shared import media, storage
from shared.db import get_session
from shared.events import publish
from shared.pagination import InvalidCursorError, paginate
from shared.security import SecureRouter

logger = logging.getLogger(__name__)

router = SecureRouter(prefix="/leads", tags=["needs"])

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
    except Exception:  # a Redis blip must never fail a need submission
        logger.warning(
            "needs: event publish failed",
            extra={"extra_fields": {"event_type": event_type}},
        )


def _validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return NeedPayloadIn.model_validate(payload).model_dump(mode="json", exclude_none=True)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="invalid_payload") from exc


def _need_out(need: Need, *, routed_count: int) -> NeedOut:
    return NeedOut(
        id=need.id,
        pincode=need.pincode,
        payload=need.payload,
        status=need.status,
        accepted_business_id=need.accepted_business_id,
        has_voice=need.voice_key is not None,
        routed_count=routed_count,
        created_at=need.created_at,
    )


@router.post("/needs", status_code=201)
async def create_need(request: Request, body: NeedCreateIn, session: SessionDep) -> NeedOut:
    user_id = _principal_user_id(request)
    clean_payload = _validate_payload(body.payload)
    try:
        await needs_service.claim_need_slot(user_id, now=datetime.now(UTC))
    except needs_service.NeedCapExceededError as exc:
        raise HTTPException(status_code=429, detail="need_cap_exceeded") from exc
    except needs_service.NeedsUnavailableError as exc:
        raise HTTPException(status_code=503, detail="need_post_unavailable") from exc
    try:
        vendors = await needs_service.route_need(session, pincode=body.pincode)
    except leads_service.NoCoverageError as exc:
        raise HTTPException(status_code=422, detail="no_coverage") from exc

    need = Need(from_user_id=user_id, pincode=body.pincode, payload=clean_payload)
    session.add(need)
    await session.flush()
    events: list[dict[str, object]] = []
    for vendor in vendors:
        inquiry = Inquiry(
            type="milk_subscription",
            from_user_id=user_id,
            business_id=vendor.id,
            payload=clean_payload,
            pincode=body.pincode,
            need_id=need.id,
        )
        session.add(inquiry)
        await session.flush()
        if vendor.owner_user_id is not None:  # unclaimed inboxes have no one to notify
            events.append(
                {
                    "user_id": str(vendor.owner_user_id),
                    "inquiry_id": str(inquiry.id),
                    "business_id": str(vendor.id),
                    "vars": {"business_name": vendor.name, "inquiry_type": "milk_subscription"},
                }
            )
    # Live feed (O11): PARENT need id only (one posted need = one row); the
    # pincode is resolved to coarse district/state and NEVER stored.
    district, state = await activity.location_for_pincode(session, body.pincode)
    await activity.record_activity(
        session,
        kind="need_posted",
        source_id=need.id,
        occurred_at=datetime.now(UTC),
        district=district,
        state=state,
    )
    out = _need_out(need, routed_count=len(vendors))
    await session.commit()  # commit BEFORE announcing (repo-wide event ordering rule)
    for event_payload in events:
        await _publish_best_effort("lead.created", event_payload)
    return out


@router.get("/needs/mine")
async def my_needs(
    request: Request, session: SessionDep, cursor: str | None = None, limit: LimitQuery = 20
) -> MyNeedPageOut:
    user_id = _principal_user_id(request)
    query = select(Need).where(Need.from_user_id == user_id)
    try:
        page = await paginate(session, query, cursor=cursor, limit=limit, descending=True)
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    need_ids = [n.id for n in page.items]
    children: list[Inquiry] = []
    if need_ids:
        rows = await session.scalars(
            select(Inquiry).where(Inquiry.need_id.in_(need_ids)).order_by(Inquiry.id)
        )
        children = list(rows)
    responses: dict[uuid.UUID, list[InquiryResponse]] = {}
    names: dict[uuid.UUID, str] = {}
    if children:
        response_rows = await session.scalars(
            select(InquiryResponse)
            .where(InquiryResponse.inquiry_id.in_([c.id for c in children]))
            .order_by(InquiryResponse.id)
        )
        for r in response_rows:
            responses.setdefault(r.inquiry_id, []).append(r)
        name_rows = await session.execute(
            select(Business.id, Business.name).where(
                Business.id.in_({c.business_id for c in children})
            )
        )
        names = {row.id: row.name for row in name_rows}
    by_need: dict[uuid.UUID, list[NeedRouteOut]] = {}
    for child in children:
        assert child.need_id is not None
        by_need.setdefault(child.need_id, []).append(
            NeedRouteOut(
                inquiry_id=child.id,
                business_id=child.business_id,
                business_name=names.get(child.business_id, ""),
                status=child.status,
                responses=[
                    ResponseOut(
                        id=r.id,
                        inquiry_id=r.inquiry_id,
                        business_user_id=r.business_user_id,
                        body=r.body,
                        created_at=r.created_at,
                    )
                    for r in responses.get(child.id, [])
                ],
            )
        )
    return MyNeedPageOut(
        items=[
            MyNeedOut(
                **_need_out(n, routed_count=len(by_need.get(n.id, []))).model_dump(),
                routes=by_need.get(n.id, []),
            )
            for n in page.items
        ],
        next_cursor=page.next_cursor,
    )


async def _transition_need(
    request: Request,
    session: AsyncSession,
    need_id: uuid.UUID,
    *,
    status: str,
    accepted_business_id: uuid.UUID | None,
) -> NeedOut:
    user_id = _principal_user_id(request)
    try:
        need = await needs_service.get_owned_need(session, user_id, need_id)
    except needs_service.NeedNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Need not found") from exc
    if need.status != "open":
        raise HTTPException(status_code=409, detail="need_closed")
    need.status = status
    need.accepted_business_id = accepted_business_id
    await needs_service.close_open_children(session, need.id)
    count = await session.scalar(
        select(func.count()).select_from(Inquiry).where(Inquiry.need_id == need.id)
    )
    out = _need_out(need, routed_count=int(count or 0))
    await session.commit()
    return out


@router.post("/needs/{need_id}/fulfill")
async def fulfill_need(
    request: Request, need_id: uuid.UUID, body: FulfillIn, session: SessionDep
) -> NeedOut:
    return await _transition_need(
        request, session, need_id, status="fulfilled", accepted_business_id=body.business_id
    )


@router.post("/needs/{need_id}/close")
async def close_need(request: Request, need_id: uuid.UUID, session: SessionDep) -> NeedOut:
    return await _transition_need(
        request, session, need_id, status="closed", accepted_business_id=None
    )


_MIME_BY_EXT = {ext: mime for mime, ext in media.AUDIO_EXTENSIONS.items()}


def _voice_response(key: str, data: bytes) -> Response:
    ext = key.rsplit(".", 1)[-1]
    return Response(
        content=data,
        media_type=_MIME_BY_EXT.get(ext, "application/octet-stream"),
        headers={"cache-control": "private, no-store"},
    )


@router.post("/needs/{need_id}/voice", status_code=201)
async def upload_need_voice(
    request: Request, need_id: uuid.UUID, session: SessionDep, file: UploadFile
) -> dict[str, str]:
    user_id = _principal_user_id(request)
    try:
        need = await needs_service.get_owned_need(session, user_id, need_id)
    except needs_service.NeedNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Need not found") from exc
    if need.status != "open":
        raise HTTPException(status_code=409, detail="need_closed")
    data = await file.read(media.MAX_AUDIO_BYTES + 1)
    try:
        blob, mime = media.validate_audio(data)
    except media.MediaError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    key = f"needs/{uuid6.uuid7().hex}.{media.AUDIO_EXTENSIONS[mime]}"
    try:
        await storage.put_object(key, blob, mime)  # store BEFORE the DB points at it
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail="storage_unavailable") from exc
    need.voice_key = key
    await session.commit()
    return {"status": "stored"}


@router.get("/needs/{need_id}/voice")
async def get_need_voice(request: Request, need_id: uuid.UUID, session: SessionDep) -> Response:
    user_id = _principal_user_id(request)
    try:
        need = await needs_service.get_owned_need(session, user_id, need_id)
    except needs_service.NeedNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Need not found") from exc
    if need.voice_key is None:
        raise HTTPException(status_code=404, detail="no_voice_note")
    data = await storage.get_object(need.voice_key)
    return _voice_response(need.voice_key, data)


@router.get("/inquiries/{inquiry_id}/voice")
async def get_inquiry_voice(
    request: Request, inquiry_id: uuid.UUID, session: SessionDep
) -> Response:
    """Routed vendor's playback path: ownership via the D18 inquiry IDOR
    contract, then follow need_id to the blob."""
    user_id = _principal_user_id(request)
    try:
        inquiry = await leads_service.get_owned_inquiry(session, user_id, inquiry_id)
    except leads_service.InquiryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Inquiry not found") from exc
    if inquiry.need_id is None:
        raise HTTPException(status_code=404, detail="no_voice_note")
    need = await session.get(Need, inquiry.need_id)
    if need is None or need.voice_key is None:
        raise HTTPException(status_code=404, detail="no_voice_note")
    data = await storage.get_object(need.voice_key)
    return _voice_response(need.voice_key, data)
