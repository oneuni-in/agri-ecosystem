"""AI assistant ORM models (A-U4 W1). Tables land in 0047.

Two tables, and neither is a source of truth.

`Chunk` is a DERIVED corpus: every row is rebuilt from content's public
`/content/feed`, which serves approved items only. The assistant therefore
cannot retrieve anything a visitor could not already read, and the human
curation gate (AG-A28) is inherited by construction rather than re-enforced
here. Dropping and rebuilding this table loses nothing.

`Usage` is a COUNTER, not a transcript. It records that a turn happened and
how it ended — never what was asked. The module rule is that nothing here
logs request bodies, and a table accumulating farmers' questions would be a
PII store nobody asked for and DPDP would have to answer for.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import TIMESTAMP, Integer, Text, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base

#: Must equal settings.ai_embedding_dims and the `vector(384)` column in
#: 0047. All three describe one fact — the embedding model's width — and a
#: mismatch is a query-time error, not a degraded result. `embedding.py`
#: asserts the running model against this at ingest.
EMBEDDING_DIMS = 384

#: Outcomes recorded in ai.usage. Enough to answer "is the assistant being
#: abused / is it refusing too much" without keeping a single question.
OUTCOME_ANSWERED = "answered"
OUTCOME_REFUSED = "refused"
OUTCOME_NO_EVIDENCE = "no_evidence"
OUTCOME_ERROR = "error"
OUTCOME_RATE_LIMITED = "rate_limited"


class Chunk(Base):
    """One retrievable passage of one approved content item."""

    __tablename__ = "chunks"
    __table_args__ = {"schema": "ai"}

    id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True)
    #: The content item's id. NOT a ForeignKey — content is another module
    #: and ai must not couple to its tables. Staleness is handled by
    #: replacing the corpus, not by cascade.
    source_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False, index=True
    )
    source_slug: Mapped[str] = mapped_column(Text, nullable=False)
    #: The publisher's name, carried so a citation can name it. Every
    #: surface on this platform states where a fact came from; an answer
    #: is not exempt.
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMS), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class Usage(Base):
    """One assistant turn, counted. No question text, ever."""

    __tablename__ = "usage"
    __table_args__ = {"schema": "ai"}

    id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(postgresql.UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), nullable=False
    )
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    refusal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
