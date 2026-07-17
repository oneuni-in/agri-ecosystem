# backend/core/alembic/versions/0017_claims_v1.py
"""D16 claims + verification-lite: claim/verification queues, claimable
businesses (owner_user_id nullable, NULL = seeded/unclaimed), business_claim
coins rule seed, claim-decision notification templates.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-16

"""
# -- THREAT/NOTES:
# downgrade data loss: drops claims and verifications (every claim decision
#   record is destroyed) and deletes the business_claim rule + the four
#   claim/verification template sets. Restoring NOT NULL on owner_user_id
#   fails if unclaimed (NULL-owner) businesses exist - pre-launch that is an
#   acceptable manual cleanup; post-launch a downgrade is an incident
#   decision. Ledger entries already awarded are NOT touched (append-only).
# locks: CREATE TABLE/TYPE on empty objects, ALTER COLUMN DROP NOT NULL on
#   businesses (metadata-only), small seed inserts. Negligible pre-launch.
# rollout: tables ship empty. 0013 already granted app_rt blanket DML +
#   default privileges across the directory schema; the explicit GRANT below
#   is belt-and-braces so the privilege intent is visible here (claims and
#   verifications are mutable, admin-decided rows - no immutability trigger,
#   matching 0016's directory tables, NOT the ledger/audit pattern).

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(name=name, schema="directory", create_type=False)


# asyncpg rejects varchar binds against enum columns - bind real enum types
# (0014's templates_table comment).
channel_enum = postgresql.ENUM(
    "in_app", "sms", "email", name="notify_channel", schema="notify", create_type=False
)
locale_enum = postgresql.ENUM(
    "en", "ta", "hi", name="notify_locale", schema="notify", create_type=False
)

templates_table = sa.table(
    "templates",
    sa.column("id", _uuid),
    sa.column("key", sa.Text),
    sa.column("channel", channel_enum),
    sa.column("locale", locale_enum),
    sa.column("subject", sa.Text),
    sa.column("body", sa.Text),
    schema="notify",
)

rules_table = sa.table(
    "rules",
    sa.column("code", sa.Text),
    sa.column("amount", sa.BigInteger),
    sa.column("daily_cap", sa.Integer),
    sa.column("weekly_cap", sa.Integer),
    sa.column("total_cap", sa.Integer),
    schema="coins",
)

# (key, locale, body) - in_app only; every key ships en+ta+hi (CI gate).
# Strict {var} rendering: producers MUST pass business_name (and reason for
# the rejected keys) or dispatch raises MissingVariableError.
SEED_TEMPLATES: list[tuple[str, str, str]] = [
    (
        "claim_approved",
        "en",
        "Your claim for {business_name} is approved. You now manage this verified listing.",
    ),
    (
        "claim_approved",
        "ta",
        "{business_name} க்கான உங்கள் உரிமைகோரல் அங்கீகரிக்கப்பட்டது. இந்த சரிபார்க்கப்பட்ட பட்டியலை இப்போது நீங்கள் நிர்வகிக்கிறீர்கள்.",  # noqa: E501
    ),
    (
        "claim_approved",
        "hi",
        "{business_name} के लिए आपका दावा स्वीकृत हो गया। अब आप इस सत्यापित लिस्टिंग का प्रबंधन करते हैं।",
    ),
    ("claim_rejected", "en", "Your claim for {business_name} was rejected: {reason}"),
    ("claim_rejected", "ta", "{business_name} க்கான உங்கள் உரிமைகோரல் நிராகரிக்கப்பட்டது: {reason}"),
    ("claim_rejected", "hi", "{business_name} के लिए आपका दावा अस्वीकृत हुआ: {reason}"),
    ("verification_approved", "en", "{business_name} is now verified on Agri."),
    ("verification_approved", "ta", "{business_name} இப்போது அக்ரியில் சரிபார்க்கப்பட்டது."),
    ("verification_approved", "hi", "{business_name} अब एग्री पर सत्यापित है।"),
    ("verification_rejected", "en", "Verification for {business_name} was rejected: {reason}"),
    ("verification_rejected", "ta", "{business_name} சரிபார்ப்பு நிராகரிக்கப்பட்டது: {reason}"),
    ("verification_rejected", "hi", "{business_name} का सत्यापन अस्वीकृत हुआ: {reason}"),
]


def upgrade() -> None:
    bind = op.get_bind()
    sa.Enum("pending", "approved", "rejected", name="claim_status", schema="directory").create(
        bind, checkfirst=True
    )
    sa.Enum("claim", "document", name="verification_method", schema="directory").create(
        bind, checkfirst=True
    )

    op.create_table(
        "claims",
        pk_column(),
        sa.Column("business_id", _uuid, sa.ForeignKey("directory.businesses.id"), nullable=False),
        sa.Column("claimant_user_id", _uuid, nullable=False, index=True),
        sa.Column(
            "status", _enum("claim_status"), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column("evidence_docs", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("decision_note", sa.Text, nullable=True),
        sa.Column("decided_by", _uuid, nullable=True),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        *timestamp_columns(),
        schema="directory",
    )
    # one live claim per (business, claimant); decided claims don't block retries
    op.create_index(
        "uq_directory_claims_one_pending",
        "claims",
        ["business_id", "claimant_user_id"],
        unique=True,
        schema="directory",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_directory_claims_status_id", "claims", ["status", "id"], schema="directory")

    op.create_table(
        "verifications",
        pk_column(),
        sa.Column("business_id", _uuid, sa.ForeignKey("directory.businesses.id"), nullable=False),
        sa.Column("method", _enum("verification_method"), nullable=False),
        sa.Column("doc_keys", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "status", _enum("claim_status"), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("decided_by", _uuid, nullable=True),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        *timestamp_columns(),
        schema="directory",
    )
    op.create_index(
        "uq_directory_verifications_one_pending",
        "verifications",
        ["business_id"],
        unique=True,
        schema="directory",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_directory_verifications_status_id",
        "verifications",
        ["status", "id"],
        schema="directory",
    )

    # NULL owner = seeded/unclaimed = claimable. The owner API (D15 service)
    # still always sets an owner on create; only seed scripts and the claim
    # flow deal in NULL.
    op.alter_column(
        "businesses", "owner_user_id", existing_type=_uuid, nullable=True, schema="directory"
    )

    # 0013's default privileges already cover new directory tables; explicit
    # grant keeps the intended app_rt profile reviewable here (0016 precedent).
    op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "directory" TO app_rt')

    # business_claim: once per BUSINESS, enforced by the worker's deterministic
    # idempotency key claim:{business_id} + the ledger UNIQUE - caps stay NULL
    # (a user may legitimately claim several businesses).
    op.bulk_insert(
        rules_table,
        [
            {
                "code": "business_claim",
                "amount": 200,
                "daily_cap": None,
                "weekly_cap": None,
                "total_cap": None,
            }
        ],
    )

    op.bulk_insert(
        templates_table,
        [
            {
                "id": uuid6.uuid7(),
                "key": key,
                "channel": "in_app",
                "locale": locale,
                "subject": None,
                "body": body,
            }
            for (key, locale, body) in SEED_TEMPLATES
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(
        "DELETE FROM notify.templates WHERE key IN "
        "('claim_approved','claim_rejected','verification_approved','verification_rejected')"
    )
    op.execute("DELETE FROM coins.rules WHERE code = 'business_claim'")
    op.drop_table("verifications", schema="directory")
    op.drop_table("claims", schema="directory")
    # fails if NULL-owner businesses exist - see THREAT block
    op.alter_column(
        "businesses", "owner_user_id", existing_type=_uuid, nullable=False, schema="directory"
    )
    sa.Enum(name="verification_method", schema="directory").drop(bind, checkfirst=True)
    sa.Enum(name="claim_status", schema="directory").drop(bind, checkfirst=True)
