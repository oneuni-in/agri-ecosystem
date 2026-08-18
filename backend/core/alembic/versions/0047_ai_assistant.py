"""A-U4 W1: the AI assistant — pgvector corpus, usage ledger, agri_ai flag.

Revision ID: 0047
Revises: 0046
Create Date: 2026-08-17

Three things, in the order they matter.

  vector extension  — pgvector, enabled here. This REQUIRES the postgres
                      image to carry the extension: docker-compose.dev.yml
                      moves from `postgres:16` to `pgvector/pgvector:pg16`
                      in the same commit. Same PG major, same data
                      directory, so an existing volume keeps working — the
                      extension is additive, not a re-init. A plain
                      postgres:16 will fail this migration at CREATE
                      EXTENSION, loudly, which is the correct outcome: a
                      silently vector-less deployment would degrade
                      retrieval to nothing and still answer.

  ai.chunks         — the retrieval corpus. Deliberately a DERIVED table
                      with no authority of its own: every row is built by
                      re-reading content's PUBLIC feed (see below), so it
                      cannot contain anything a visitor could not already
                      read, and it can be dropped and rebuilt at any time.

  ai.usage          — the per-user turn/day ledger the rate limits read.

WHY THE CORPUS IS DERIVED, AND WHY THAT IS A SAFETY PROPERTY.

`modules.ai` is forbidden from importing `modules.content` (import-linter
independence contract) and from reading another module's tables directly.
The ingest therefore walks `GET /content/feed`, the same public, cursor-
paginated endpoint the /knowledge page uses.

That constraint turns out to be the feature. The public feed serves
APPROVED items only — the human-curation gate A-U3 built (AG-A28) — so the
assistant's corpus inherits that gate BY CONSTRUCTION rather than by
remembering to filter. There is no query anywhere in modules/ai that could
accidentally retrieve a pending article, because the ingest never has
access to one. A future change that widened the corpus would have to widen
the public feed first, which is a visible, reviewable act.

EMBEDDING WIDTH IS LOAD-BEARING.

`embedding vector(384)` is BAAI/bge-small-en-v1.5 (settings.ai_embedding_dims).
Changing the embedding model changes this width and requires a migration
plus a full re-embed — mixing widths is not a degraded search, it is an
error at query time. The dimension is asserted against settings at ingest.

INDEX CHOICE. No ANN index (ivfflat/hnsw) is created, on purpose. The
corpus is 15 approved documents at build time; an approximate index over a
few hundred chunks is slower and less accurate than the exact scan it
replaces, and ivfflat additionally needs training data it does not have
yet. Exact cosine distance over this corpus is sub-millisecond. Add hnsw
when the corpus justifies it — that is a one-line migration, and doing it
now would be guessing.
"""

# -- THREAT/NOTES:
# - New `ai` schema with two tables, plus CREATE EXTENSION vector. No
#   existing table is touched, so no rewrite and no lock on live data.
# - REQUIRES the pgvector image (docker-compose.dev.yml moves postgres:16 ->
#   pgvector/pgvector:pg16 in this commit). On a plain postgres:16 this fails
#   at CREATE EXTENSION rather than silently producing a vector-less
#   deployment that would retrieve nothing and still answer. NOTE for
#   whoever swaps the image on an existing volume: the pgvector image ships
#   a different glibc, so Postgres warns about a collation-version mismatch
#   — run `REINDEX DATABASE agri` then `ALTER DATABASE agri REFRESH
#   COLLATION VERSION` once, or text index ordering is subtly wrong.
# - downgrade drops both tables and the flag row; the extension is
#   deliberately kept (another schema may come to depend on it, and DROP
#   EXTENSION would take their columns with it). ai.chunks is DERIVED and
#   rebuildable via scripts/ai_ingest.py, so dropping it loses nothing;
#   ai.usage loses per-user counters, which are operational, not user data.
# - locks: CREATE SCHEMA / CREATE TABLE / CREATE EXTENSION take catalog
#   locks only. No ANN index is built (see the docstring), so there is no
#   long index build to hold anything.
# - PII: ai.usage deliberately stores NO question text — only a user id, a
#   conversation id, an outcome and a timestamp. The ai module must never
#   log request bodies (modules/ai/CLAUDE.md), and a ledger accumulating
#   farmers' questions would be a DPDP liability nobody asked for.
# - Moderation: ai.chunks is built exclusively from content's PUBLIC feed,
#   which serves approved items only, so the human curation gate (AG-A28) is
#   inherited by construction — there is no query in modules/ai that could
#   reach a pending item.
# - Explicit per-table GRANTs to app_rt (0023/0027/0038/0045/0046
#   precedent), never a blanket GRANT. ai.chunks is SELECT-only to the
#   runtime role: the corpus is written by the ingest under the migration
#   role, so nothing on the request path — including anything an LLM could
#   influence — holds a grant that could write to the corpus it reads from.
# - The agri_ai flag enters false (fail-closed, D3). Flipping it is the only
#   change needed to ship the assistant.

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ai")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # The content item this chunk came from. NOT a foreign key: content
        # lives in another module and ai must not couple to its tables. A
        # deleted or un-approved item is handled by re-ingest replacing the
        # whole corpus, not by cascade.
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_slug", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        # Chunk ordinal within its source, so a citation can point at the
        # right part of a long guide.
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="ai",
    )
    # The ARRAY column above is replaced by a real pgvector column here.
    # Declaring it as ARRAY in create_table then altering keeps the table
    # definition readable to SQLAlchemy tooling that does not know pgvector.
    op.execute("ALTER TABLE ai.chunks DROP COLUMN embedding")
    op.execute("ALTER TABLE ai.chunks ADD COLUMN embedding vector(384)")

    op.create_index("ix_ai_chunks_source", "chunks", ["source_id"], schema="ai")

    op.create_table(
        "usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The conversation this turn belongs to, so the per-conversation
        # turn cap can be counted without storing the conversation itself.
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Deliberately NOT the question text. The ai module must never log
        # request bodies (modules/ai/CLAUDE.md), and a usage ledger that
        # accumulates what farmers asked is a PII store nobody asked for.
        # We keep counts and outcomes, never content.
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("refusal_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="ai",
    )
    op.create_index("ix_ai_usage_user_created", "usage", ["user_id", "created_at"], schema="ai")
    op.create_index("ix_ai_usage_conversation", "usage", ["conversation_id"], schema="ai")

    # Explicit per-table GRANTs to the runtime role (the 0023/0027/0038/
    # 0045/0046 precedent), never a blanket GRANT ON ALL TABLES — this
    # schema will hold more. Without these the API runs as app_rt and
    # cannot read its own corpus, which surfaces as an assistant that
    # answers "I have no sources" for every question ever asked.
    #
    # chunks is READ-ONLY to the runtime role on purpose: the corpus is
    # rebuilt by scripts/ai_ingest.py under the migration role, so nothing
    # on the request path — including anything an LLM could influence — has
    # a grant that would let it write to the corpus it retrieves from.
    op.execute("GRANT USAGE ON SCHEMA ai TO app_rt")
    op.execute("GRANT SELECT ON ai.chunks TO app_rt")
    op.execute("GRANT SELECT, INSERT ON ai.usage TO app_rt")

    # The flag enters OFF (D3 mechanism, fail-closed), and stays OFF until
    # the owner signs off on a LIVE red-team run. The build prompt's
    # requirement is that flipping this flag is the only change needed —
    # nothing else in the assistant is conditional on it.
    op.execute(
        "INSERT INTO public.feature_flags (key, enabled, description) "
        "VALUES ('agri_ai', false, "
        "'A-U4 W1 agri AI assistant. OFF until the owner signs off on a live "
        "red-team run (docs/security/agri-ai-redteam.md).') "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM public.feature_flags WHERE key = 'agri_ai'")
    op.drop_table("usage", schema="ai")
    op.drop_table("chunks", schema="ai")
    # The extension is deliberately NOT dropped: another schema may come to
    # depend on it, and DROP EXTENSION would take their columns with it.
