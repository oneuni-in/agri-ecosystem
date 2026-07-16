"""D15 directory: businesses, branches, categories, coverage - the shared
directory engine (org/place profiles; Milk.in is the first consumer).
Mutable, owner-scoped business data: no immutability trigger by design.

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-15

"""
# -- THREAT/NOTES:
# downgrade data loss: drops all five directory tables and four enums - every
#   business, branch, category link and coverage row is destroyed. Acceptable
#   pre-launch; post-launch a downgrade is an incident decision. The
#   `directory` schema itself belongs to 0001 and is left in place.
# locks: CREATE TABLE/TYPE on empty objects + seed inserts into a fresh
#   categories table; negligible.
# rollout: tables ship empty except seeded categories. 0013 already granted
#   app_rt blanket DML + default privileges across the directory schema; the
#   explicit GRANT below is belt-and-braces so the privilege intent is
#   visible in this migration (D15 integration surface).

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, soft_delete_column, timestamp_columns

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)

# (slug, english label, sort_order) - flat, vertical-agnostic v1 set
SEED_CATEGORIES = [
    ("farm", "Farm", 10),
    ("dairy", "Dairy", 20),
    ("shop", "Shop", 30),
    ("lab", "Lab", 40),
    ("nursery", "Nursery", 50),
    ("equipment", "Equipment", 60),
    ("service", "Service", 70),
    ("other", "Other", 80),
]

ENUMS = (
    ("business_type", ("vendor", "shop", "lab", "farm")),
    ("business_status", ("active", "suspended")),
    ("verification_status", ("unverified", "pending", "verified")),
    ("subscription_tier", ("free", "premium")),
)


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(name=name, schema="directory", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS:
        sa.Enum(*values, name=name, schema="directory").create(bind, checkfirst=True)

    op.create_table(
        "businesses",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        sa.Column("owner_user_id", _uuid, nullable=False, index=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("slug", sa.Text, nullable=False, unique=True, index=True),
        sa.Column("description", postgresql.JSONB, nullable=True),
        sa.Column("type", _enum("business_type"), nullable=False),
        sa.Column("status", _enum("business_status"), nullable=False, server_default="active"),
        sa.Column(
            "verification_status",
            _enum("verification_status"),
            nullable=False,
            server_default="unverified",
        ),
        sa.Column(
            "subscription_tier",
            _enum("subscription_tier"),
            nullable=False,
            server_default="free",
        ),
        sa.Column("primary_pincode", sa.Text, nullable=False, index=True),
        schema="directory",
    )

    op.create_table(
        "branches",
        pk_column(),
        *timestamp_columns(),
        soft_delete_column(),
        sa.Column(
            "business_id",
            _uuid,
            sa.ForeignKey("directory.businesses.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("address", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("district", sa.Text, nullable=False),
        sa.Column("pincode", sa.Text, nullable=False, index=True),
        sa.Column("lat", sa.Numeric(9, 6), nullable=True),
        sa.Column("lng", sa.Numeric(9, 6), nullable=True),
        sa.Column("phone", sa.Text, nullable=True),
        sa.Column("whatsapp", sa.Text, nullable=True),
        sa.Column("hours", postgresql.JSONB, nullable=False, server_default="{}"),
        schema="directory",
    )

    op.create_table(
        "categories",
        pk_column(),
        *timestamp_columns(),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        sa.Column("name", postgresql.JSONB, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        schema="directory",
    )

    op.create_table(
        "business_categories",
        pk_column(),
        *timestamp_columns(),
        sa.Column("business_id", _uuid, sa.ForeignKey("directory.businesses.id"), nullable=False),
        sa.Column("category_id", _uuid, sa.ForeignKey("directory.categories.id"), nullable=False),
        sa.UniqueConstraint("business_id", "category_id", name="uq_business_categories_pair"),
        schema="directory",
    )

    op.create_table(
        "business_coverage",
        pk_column(),
        *timestamp_columns(),
        sa.Column("business_id", _uuid, sa.ForeignKey("directory.businesses.id"), nullable=False),
        sa.Column("pincode", sa.Text, nullable=False),
        sa.UniqueConstraint("business_id", "pincode", name="uq_business_coverage_pair"),
        schema="directory",
    )
    # THREAT: covers(pincode) is the hot public query - it enters through this index.
    op.create_index(
        "ix_directory_business_coverage_pincode",
        "business_coverage",
        ["pincode"],
        schema="directory",
    )

    op.bulk_insert(
        sa.table(
            "categories",
            sa.column("id", _uuid),
            sa.column("slug", sa.Text),
            sa.column("name", postgresql.JSONB),
            sa.column("sort_order", sa.Integer),
            schema="directory",
        ),
        [
            {"id": uuid6.uuid7(), "slug": slug, "name": {"en": label}, "sort_order": order}
            for (slug, label, order) in SEED_CATEGORIES
        ],
    )

    # 0013's per-schema default privileges already cover these tables; the
    # explicit grant makes the intended app_rt profile reviewable here.
    op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "directory" TO app_rt')


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("business_coverage", schema="directory")
    op.drop_table("business_categories", schema="directory")
    op.drop_table("branches", schema="directory")
    op.drop_table("categories", schema="directory")
    op.drop_table("businesses", schema="directory")
    for name, _values in reversed(ENUMS):
        sa.Enum(name=name, schema="directory").drop(bind, checkfirst=True)
