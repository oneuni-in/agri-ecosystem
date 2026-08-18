"""A-U4 W1 — assistant orchestration.

The request path, and the order is the design:

    flag OFF? ────────────────────────────► 404 (feature_disabled)
    per-user limits ──────────────────────► 429
    safety.check_question ────────────────► refusal + route  (no model call)
    retrieve (pgvector, approved corpus) ─► no evidence? say so (no model call)
    model call (fenced sources + tools) ──►
    safety.check_answer ──────────────────► leak/link/dose? discard whole
    return answer + citations built IN CODE

Two of those arrows are the point. A refused question never reaches the
model, so a dosage request costs nothing and cannot be talked around. And an
answer with no retrieved evidence is never generated at all — the assistant
says it has nothing rather than falling back on model memory, because a
confident guess about a crop is how a farmer loses a season.

Citations are assembled here from the retrieved rows' own metadata, never
from model output. The model cites by number; the names, slugs and links are
ours. That is why `safety.check_answer` can reject any URL the model emits:
it never needed to emit one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import uuid6
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from settings import get_settings
from shared.flags import flag_enabled

from . import safety
from .embedding import embed_query
from .models import (
    OUTCOME_ANSWERED,
    OUTCOME_ERROR,
    OUTCOME_NO_EVIDENCE,
    OUTCOME_RATE_LIMITED,
    OUTCOME_REFUSED,
    Chunk,
    Usage,
)
from .safety import RefusalReason
from .tools import anthropic_tool_schemas, call_tool

__all__ = ["AssistantReply", "Citation", "answer_question", "assistant_enabled"]

#: How many tool round-trips one question may drive. Two is enough for
#: "look up the commodity list, then fetch one commodity"; more than that
#: and the model is exploring, not answering, on our budget.
_MAX_TOOL_ROUNDS = 2


@dataclass
class Citation:
    title: str
    slug: str
    source_name: str
    kind: str


@dataclass
class AssistantReply:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    refused: bool = False
    reason: str | None = None
    route: str | None = None


async def assistant_enabled(session: AsyncSession) -> bool:
    return await flag_enabled("agri_ai", session=session)


# ── per-user limits ─────────────────────────────────────────────────────────


async def _over_limit(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> str | None:
    """Turn and day caps, counted from the usage ledger.

    These sit ON TOP OF SecureRouter's global rate limit because a model call
    is not a page read: it costs real money and it is the expensive thing to
    abuse. Both caps count refusals too — otherwise someone could probe the
    safety layer for free, which is exactly the traffic we least want to
    subsidise.
    """
    settings = get_settings()
    since = datetime.now(UTC) - timedelta(days=1)

    day_count = await session.scalar(
        select(func.count())
        .select_from(Usage)
        .where(Usage.user_id == user_id, Usage.created_at >= since)
    )
    if (day_count or 0) >= settings.ai_max_questions_per_day:
        return "daily"

    # Scoped by user_id AND conversation_id. The conversation id is
    # CLIENT-SUPPLIED, so counting on it alone makes one caller's limit
    # depend on another caller's rows: someone who supplied a conversation id
    # that was not theirs would have that conversation's turns counted
    # against them, and could learn whether a given id had reached the cap.
    # UUIDs make that impractical to exploit, which is why it is a Low and
    # not a High — but a limit check has no business reading another user's
    # rows at all. Found in the A-U4 W5 audit of W1's own code.
    turn_count = await session.scalar(
        select(func.count())
        .select_from(Usage)
        .where(Usage.user_id == user_id, Usage.conversation_id == conversation_id)
    )
    if (turn_count or 0) >= settings.ai_max_turns_per_conversation:
        return "turns"
    return None


async def _record(
    session: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    outcome: str,
    reason: str | None = None,
) -> None:
    """Count the turn. Never the question — see models.Usage."""
    session.add(
        Usage(
            id=uuid6.uuid7(),
            user_id=user_id,
            conversation_id=conversation_id,
            outcome=outcome,
            refusal_reason=reason,
        )
    )
    await session.flush()


# ── retrieval ───────────────────────────────────────────────────────────────


async def _retrieve(session: AsyncSession, question: str) -> list[Chunk]:
    """Exact cosine search over the approved corpus.

    The floor here is a QUALITY floor only. It was designed to double as a
    scope check; measurement killed that idea — off-domain queries retrieve
    at similarities indistinguishable from real ones on a corpus this small
    (settings.ai_similarity_floor carries the numbers). Scope is enforced
    upstream, by safety.check_question, before this function is reached.
    """
    vector = embed_query(question)
    if vector is None:
        return []
    settings = get_settings()
    # `<=>` is pgvector cosine distance; similarity = 1 - distance.
    distance = Chunk.embedding.cosine_distance(vector)
    rows = await session.execute(
        select(Chunk, distance.label("distance"))
        .where(Chunk.embedding.isnot(None))
        .order_by(distance)
        .limit(settings.ai_retrieval_k)
    )
    kept: list[Chunk] = []
    for chunk, dist in rows.all():
        if dist is None:
            continue
        if (1.0 - float(dist)) >= settings.ai_similarity_floor:
            kept.append(chunk)
    return kept


def _build_user_turn(question: str, chunks: list[Chunk]) -> str:
    """The user turn: fenced sources, then the question.

    Everything attacker-influenced is inside a fence and labelled as a
    source. The question is appended after, unfenced, because it is the
    thing being asked — but it has already passed check_question, so it is
    not carrying an instruction override either.
    """
    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        body = f"[{i}] {chunk.title}\n{chunk.body}"
        parts.append(safety.fence_untrusted(body, label=f"{chunk.source_name}#{i}"))
    parts.append(f"Question: {question}")
    return "\n\n".join(parts)


# ── the model call ──────────────────────────────────────────────────────────


async def _ask_model(user_turn: str) -> str:
    """One answer from Claude, with the read-only tools attached.

    Adaptive thinking is on by default on Opus 5 and `budget_tokens` is
    rejected there, so depth is controlled with `effort` — pinned low
    because this is a short grounded answer over six passages, not a
    reasoning task, and latency is what a farmer on a slow connection feels.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("anthropic_api_key is not configured")

    from anthropic import AsyncAnthropic
    from anthropic.types import MessageParam, OutputConfigParam, ToolParam

    client = AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=settings.ai_timeout_seconds)
    messages: list[MessageParam] = [{"role": "user", "content": user_turn}]

    for _ in range(_MAX_TOOL_ROUNDS + 1):
        response = await client.messages.create(
            model=settings.ai_model,
            max_tokens=settings.ai_max_tokens,
            system=safety.SYSTEM_PROMPT,
            # cast: effort is a config string and the SDK types it as a
            # Literal. Validating it here would duplicate the API's own
            # validation without adding a guarantee — a bad value is a 400
            # on the first call, which is loud enough.
            output_config=cast("OutputConfigParam", {"effort": settings.ai_effort}),
            tools=cast("list[ToolParam]", anthropic_tool_schemas()),
            messages=messages,
        )
        if response.stop_reason != "tool_use":
            return "".join(block.text for block in response.content if block.type == "text")

        # Execute every requested tool and return ALL results in one user
        # message — splitting them teaches the model to stop calling tools
        # in parallel.
        messages.append({"role": "assistant", "content": response.content})
        results: list[Any] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            ok, payload = await call_tool(block.name, dict(block.input or {}))
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": payload,
                    "is_error": not ok,
                }
            )
        messages.append({"role": "user", "content": results})

    # Out of tool rounds without an answer. Say so rather than returning the
    # last half-formed thing.
    return ""


# ── the entry point ─────────────────────────────────────────────────────────

_REFUSAL_COPY: dict[RefusalReason, str] = {
    RefusalReason.REGULATED_DOSAGE: (
        "I can't give dosages or application rates — getting that wrong costs a "
        "crop. Check the product label, and call the Kisan Call Centre on "
        "1800-180-1551 for a recommendation for your field."
    ),
    RefusalReason.REGULATED_SCHEME: (
        "I can't check who qualifies for a scheme — that depends on your own "
        "records and the current rules. The scheme pages link to the official "
        "portals, which are the only place that can tell you."
    ),
    RefusalReason.REGULATED_LOAN: (
        "I can't advise on loans or credit. For farm credit questions, the Kisan "
        "Call Centre and your bank's agriculture desk are the right people."
    ),
    RefusalReason.OUT_OF_SCOPE: (
        "I only answer questions about Indian agriculture — crops, mandi prices, "
        "weather, livestock and farm practice."
    ),
    RefusalReason.INJECTION_ATTEMPT: (
        "I can only answer farming questions from agri.in's published guides."
    ),
    RefusalReason.TOO_LONG: "That question is too long — please shorten it.",
    RefusalReason.EMPTY: "Please type a question.",
}


async def answer_question(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    question: str,
) -> AssistantReply:
    settings = get_settings()

    limit = await _over_limit(session, user_id, conversation_id)
    if limit is not None:
        await _record(session, user_id, conversation_id, OUTCOME_RATE_LIMITED, limit)
        return AssistantReply(
            answer=(
                "You've reached today's question limit."
                if limit == "daily"
                else "This conversation has reached its length limit — start a new one."
            ),
            refused=True,
            reason=f"rate_limited_{limit}",
        )

    verdict = safety.check_question(question, max_chars=settings.ai_max_question_chars)
    if not verdict.allowed:
        reason = verdict.reason or RefusalReason.OUT_OF_SCOPE
        await _record(session, user_id, conversation_id, OUTCOME_REFUSED, reason.value)
        return AssistantReply(
            answer=_REFUSAL_COPY.get(reason, _REFUSAL_COPY[RefusalReason.OUT_OF_SCOPE]),
            refused=True,
            reason=reason.value,
            route=verdict.route,
        )

    chunks = await _retrieve(session, question)
    if not chunks:
        await _record(session, user_id, conversation_id, OUTCOME_NO_EVIDENCE)
        return AssistantReply(
            answer=(
                "I don't have a published guide that covers that yet. Browsing "
                "the knowledge section or calling the Kisan Call Centre on "
                "1800-180-1551 will get you further than a guess from me."
            ),
            refused=True,
            reason="no_evidence",
            route="/knowledge",
        )

    try:
        raw = await _ask_model(_build_user_turn(question, chunks))
    except Exception:  # noqa: BLE001 - upstream/model failure must not 500
        await _record(session, user_id, conversation_id, OUTCOME_ERROR)
        return AssistantReply(
            answer="The assistant is unavailable right now. Please try again shortly.",
            refused=True,
            reason="unavailable",
        )

    if not raw.strip():
        await _record(session, user_id, conversation_id, OUTCOME_ERROR)
        return AssistantReply(
            answer="I couldn't put together an answer for that one.",
            refused=True,
            reason="empty_answer",
        )

    outbound = safety.check_answer(raw)
    if not outbound.allowed:
        # Discarded WHOLE. A partially-redacted leak is still a leak, and an
        # answer we would have to censor is one we should not send.
        reason = outbound.reason or RefusalReason.INJECTION_ATTEMPT
        await _record(session, user_id, conversation_id, OUTCOME_REFUSED, reason.value)
        return AssistantReply(
            answer=_REFUSAL_COPY.get(reason, _REFUSAL_COPY[RefusalReason.OUT_OF_SCOPE]),
            refused=True,
            reason=reason.value,
            route=outbound.route,
        )

    await _record(session, user_id, conversation_id, OUTCOME_ANSWERED)
    return AssistantReply(
        answer=raw.strip(),
        citations=[
            Citation(
                title=c.title,
                slug=c.source_slug,
                source_name=c.source_name,
                kind=c.kind,
            )
            for c in chunks
        ],
    )
