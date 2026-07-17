"""Claim flow, user side (D16): submit a claim with evidence images, list my
claims, read my own evidence. Evidence is NEVER public - the GET route 404s
anyone but the claimant (admins use /admin/directory). Never log request
bodies or query strings (PII)."""

import uuid
from typing import Annotated

from fastapi import Depends, File, HTTPException, Path, Query, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import claims, service
from modules.directory.models import Claim, Verification
from modules.directory.schemas import ClaimOut, ClaimPageOut, VerificationOut
from shared import media, storage
from shared.db import get_session
from shared.pagination import DEFAULT_PAGE_SIZE, InvalidCursorError
from shared.security import SecureRouter

router = SecureRouter(prefix="/directory", tags=["directory-claims"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LimitQuery = Annotated[int, Query(ge=1, le=100)]


def _principal_user_id(request: Request) -> uuid.UUID:
    principal = request.state.principal  # set by require_auth (shared.security)
    user_id = principal.user_id
    assert isinstance(user_id, uuid.UUID)
    return user_id


def _claim_out(claim: Claim) -> ClaimOut:
    return ClaimOut(
        id=claim.id,
        business_id=claim.business_id,
        claimant_user_id=claim.claimant_user_id,
        status=claim.status,
        evidence_count=len(claim.evidence_docs),
        decision_note=claim.decision_note,
        created_at=claim.created_at,
        decided_at=claim.decided_at,
    )


def _verification_out(v: Verification) -> VerificationOut:
    return VerificationOut(
        id=v.id,
        business_id=v.business_id,
        method=v.method,
        status=v.status,
        notes=v.notes,
        doc_count=len(v.doc_keys),
        created_at=v.created_at,
        decided_at=v.decided_at,
    )


async def _store_evidence(files: list[UploadFile]) -> list[str]:
    """Validate + re-encode ALL files first, then store - a rejected file
    must not leave earlier files orphaned in the bucket."""
    if not 1 <= len(files) <= claims.MAX_EVIDENCE_DOCS:
        raise HTTPException(
            status_code=422,
            detail=f"between 1 and {claims.MAX_EVIDENCE_DOCS} evidence images required",
        )
    processed: list[tuple[str, bytes]] = []
    for upload in files:
        data = await upload.read(media.MAX_IMAGE_BYTES + 1)
        try:
            jpeg, _ = media.reencode_image(data)
        except media.MediaError as exc:
            raise HTTPException(status_code=422, detail=exc.code) from exc
        processed.append((claims.evidence_object_key(), jpeg))
    try:
        for key, blob in processed:  # storage before DB (avatar precedent)
            await storage.put_object(key, blob, "image/jpeg")
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail="storage unavailable") from exc
    return [key for key, _ in processed]


@router.post("/businesses/{business_id}/claim", status_code=201)
async def submit_claim(
    request: Request,
    business_id: uuid.UUID,
    session: SessionDep,
    files: Annotated[list[UploadFile], File(description="evidence images (1-5, jpeg/png/webp)")],
) -> ClaimOut:
    evidence_docs = await _store_evidence(files)
    try:
        claim = await claims.submit_claim(
            session,
            claimant_user_id=_principal_user_id(request),
            business_id=business_id,
            evidence_docs=evidence_docs,
        )
    except claims.ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    except claims.ClaimError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    return _claim_out(claim)


@router.get("/claims")
async def list_my_claims(
    request: Request,
    session: SessionDep,
    cursor: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
) -> ClaimPageOut:
    try:
        page = await claims.list_my_claims(
            session, _principal_user_id(request), cursor=cursor, limit=limit
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    return ClaimPageOut(items=[_claim_out(c) for c in page.items], next_cursor=page.next_cursor)


@router.get("/claims/{claim_id}/evidence/{index}")
async def get_claim_evidence(
    request: Request,
    claim_id: uuid.UUID,
    index: Annotated[int, Path(ge=0)],
    session: SessionDep,
) -> Response:
    claim = await claims.get_claim(session, claim_id)
    # IDOR: someone else's claim and a missing claim are the same 404
    if claim is None or claim.claimant_user_id != _principal_user_id(request):
        raise HTTPException(status_code=404, detail="Claim not found")
    if index >= len(claim.evidence_docs):
        raise HTTPException(status_code=404, detail="Claim not found")
    try:
        data = await storage.get_object(claim.evidence_docs[index])
    except storage.StorageError as exc:
        raise HTTPException(status_code=503, detail="storage unavailable") from exc
    return Response(
        content=data, media_type="image/jpeg", headers={"cache-control": "private, no-store"}
    )


@router.post("/businesses/{business_id}/verification", status_code=201)
async def request_verification(
    request: Request,
    business_id: uuid.UUID,
    session: SessionDep,
    files: Annotated[list[UploadFile], File(description="verification documents (1-5 images)")],
) -> VerificationOut:
    doc_keys = await _store_evidence(files)
    try:
        verification = await claims.request_verification(
            session,
            owner_user_id=_principal_user_id(request),
            business_id=business_id,
            doc_keys=doc_keys,
        )
    except service.BusinessNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Business not found") from exc
    except claims.ClaimError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    return _verification_out(verification)
