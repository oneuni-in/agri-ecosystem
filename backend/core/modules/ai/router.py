"""AI assistant routes (A-U4 W1).

NOT public. The assistant costs money per call and carries per-user turn and
day limits, both of which need a principal to count against — an anonymous
assistant is an unmetered one. The Ask-AI entry surface on the home page is
public; asking a question requires a session.

The flag is consumed HERE, at the API boundary, exactly as `agri_today` is:
with `agri_ai` OFF the route 404s with `feature_disabled`, the web app reads
that as "not available" and renders the honest coming-soon state. Flipping
the flag is the only change needed to ship the assistant — nothing else in
this module is conditional on it.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.security import SecureRouter

from .service import answer_question, assistant_enabled

SessionDep = Annotated[AsyncSession, Depends(get_session)]

router = SecureRouter(prefix="/ai", tags=["ai"])


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    #: Client-supplied so a conversation can span requests without us
    #: storing one. The turn cap counts rows carrying this id; a visitor
    #: who rotates it to dodge the cap still meets the daily cap, which is
    #: counted per user and cannot be rotated.
    conversation_id: uuid.UUID | None = None


class CitationOut(BaseModel):
    title: str
    slug: str
    source_name: str
    kind: str


class AskOut(BaseModel):
    answer: str
    citations: list[CitationOut] = []
    refused: bool = False
    reason: str | None = None
    #: Where the UI should send the visitor when we decline — a refusal that
    #: names the verified surface is the point of refusing.
    route: str | None = None
    conversation_id: uuid.UUID


def _caller(request: Request) -> uuid.UUID:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "auth_required")
    return uuid.UUID(str(principal.user_id))


class StatusOut(BaseModel):
    enabled: bool


# public=True: whether a feature is switched on is not a secret, and the web
# app needs it to choose between the chat and the honest not-yet state.
#
# It exists because the private /ask route CANNOT answer the question: the
# SecureRouter auth dependency runs BEFORE the handler, so an unauthenticated
# probe gets 401 whether the flag is on or off. Inferring the flag from that
# 401 is exactly the bug this route was added to fix — the web app was
# rendering a composer for a disabled assistant.
#
# It returns one boolean and reads nothing about the caller.
@router.get("/status", public=True)
async def status_(session: SessionDep) -> StatusOut:
    return StatusOut(enabled=await assistant_enabled(session))


@router.post("/ask")
async def ask(session: SessionDep, request: Request, body: AskIn) -> AskOut:
    if not await assistant_enabled(session):
        # Same shape as market_data's flag-off 404 — the web app already
        # knows how to read this and render the honest Soon state.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "feature_disabled")

    conversation_id = body.conversation_id or uuid.uuid4()
    reply = await answer_question(
        session,
        user_id=_caller(request),
        conversation_id=conversation_id,
        question=body.question,
    )
    return AskOut(
        answer=reply.answer,
        citations=[CitationOut(**c.__dict__) for c in reply.citations],
        refused=reply.refused,
        reason=reply.reason,
        route=reply.route,
        conversation_id=conversation_id,
    )
