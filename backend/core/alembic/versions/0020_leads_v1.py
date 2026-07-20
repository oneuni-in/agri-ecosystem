# backend/core/alembic/versions/0020_leads_v1.py
"""leads v1: inquiries + responses + append-only contact-reveal log + lead
notify templates.

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-19

"""
# -- THREAT/NOTES:
# - downgrade drops inquiries/responses/contact_reveals (lead + DPDP-log loss)
#   and the lead_* notify templates.
# - contact_reveals is append-only by grant (REVOKE UPDATE, DELETE from
#   app_rt) - the reveal log is evidence, not state. It stores IDs only;
#   adding a phone column would be a DPDP violation, refuse in review.
# - leads schema + its app_rt default privileges already exist (0001 + 0013);
#   explicit per-table grants below keep the profile reviewable (0018/0019
#   precedent) - NEVER a blanket GRANT ON ALL TABLES IN SCHEMA, which would
#   silently re-grant UPDATE/DELETE on any already-append-only table sharing
#   the schema.

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)

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

# producers MUST pass business_name and, for lead_received, inquiry_type -
# strict {var} rendering (no extra/missing placeholders).
SEED_TEMPLATES: list[tuple[str, str, str]] = [
    ("lead_received", "en", "New {inquiry_type} enquiry for {business_name}."),
    ("lead_received", "ta", "{business_name}க்கு புதிய {inquiry_type} விசாரணை வந்துள்ளது."),
    ("lead_received", "hi", "{business_name} के लिए नई {inquiry_type} पूछताछ आई है."),
    ("lead_response", "en", "{business_name} replied to your enquiry."),
    ("lead_response", "ta", "{business_name} உங்கள் விசாரணைக்கு பதிலளித்துள்ளது."),
    ("lead_response", "hi", "{business_name} ने आपकी पूछताछ का जवाब दिया है."),
]


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM("contact", "milk_subscription", name="inquiry_type", schema="leads").create(
        bind, checkfirst=True
    )
    postgresql.ENUM("new", "responded", "closed", name="inquiry_status", schema="leads").create(
        bind, checkfirst=True
    )
    type_col = postgresql.ENUM(name="inquiry_type", schema="leads", create_type=False)
    status_col = postgresql.ENUM(name="inquiry_status", schema="leads", create_type=False)

    op.create_table(
        "inquiries",
        pk_column(),
        sa.Column("type", type_col, nullable=False),
        sa.Column("from_user_id", _uuid, nullable=True),
        sa.Column("business_id", _uuid, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("status", status_col, nullable=False, server_default="new"),
        sa.Column("pincode", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=True),
        *timestamp_columns(),
        schema="leads",
    )
    op.create_index(
        "ix_leads_inquiries_business_id_id", "inquiries", ["business_id", "id"], schema="leads"
    )
    op.create_index(
        "ix_leads_inquiries_from_user_id_id",
        "inquiries",
        ["from_user_id", "id"],
        schema="leads",
    )

    op.create_table(
        "responses",
        pk_column(),
        sa.Column("inquiry_id", _uuid, sa.ForeignKey("leads.inquiries.id"), nullable=False),
        sa.Column("business_user_id", _uuid, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        *timestamp_columns(),
        schema="leads",
    )
    op.create_index(
        "ix_leads_responses_inquiry_id_id", "responses", ["inquiry_id", "id"], schema="leads"
    )

    op.create_table(
        "contact_reveals",
        pk_column(),
        sa.Column("user_id", _uuid, nullable=False),
        sa.Column("business_id", _uuid, nullable=False),
        sa.Column("branch_id", _uuid, nullable=False),
        *timestamp_columns(),
        schema="leads",
    )
    op.create_index(
        "ix_leads_contact_reveals_user_id_created_at",
        "contact_reveals",
        ["user_id", "created_at"],
        schema="leads",
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON leads.inquiries TO app_rt")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON leads.responses TO app_rt")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON leads.contact_reveals TO app_rt")
    # contact_reveals is append-only BY GRANT - see THREAT block above.
    op.execute("REVOKE UPDATE, DELETE ON leads.contact_reveals FROM app_rt")

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
    op.execute("DELETE FROM notify.templates WHERE key IN ('lead_received', 'lead_response')")
    op.drop_table("responses", schema="leads")
    op.drop_table("inquiries", schema="leads")
    op.drop_table("contact_reveals", schema="leads")
    sa.Enum(name="inquiry_status", schema="leads").drop(bind, checkfirst=True)
    sa.Enum(name="inquiry_type", schema="leads").drop(bind, checkfirst=True)
