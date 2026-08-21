"""farm profile + self-description (ID-U1 W5)

A7's "What describes you?" section. A farmer's land, livestock and irrigation
live on the IDENTITY profile rather than in any one vertical, because there is
one farm and all three sites read it: cattle feed milk.in, crops feed agri.in's
advisories, certification feeds theorganic.in. A business answers here by being
routed to its directory listing — nothing about a shop is collected on a
personal AgriID.

Revision ID: 0058
Revises: 0057
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0058"
down_revision: str | None = "0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# -- THREAT/NOTES:
# - One new table plus one nullable JSONB column on identity.profiles with a
#   server default. Postgres 11+ records a default as catalog metadata rather
#   than rewriting the table, so the ALTER is a brief lock and no row is
#   touched.
# - EVERY farm column is nullable and stays nullable. This is a section a
#   farmer may answer in any order, or not at all, and a NOT NULL here would
#   turn "I did not say" into a lie about zero animals.
# - Never public. No route serves these fields to anyone but their owner:
#   IdentityPublicSchema's guard governs what leaves this module, the admin
#   user reader does not select them, and directory's vendor surfaces cannot
#   reach identity's tables at all (import-linter). They ARE included in the
#   DPDP export, which goes only to the subject.
# - Blast radius if wrong: the "What describes you?" section renders empty and
#   nothing else changes. No score, no coins, no ranking and no advisory
#   depends on these values yet — completion_score deliberately ignores them,
#   so adding farm data cannot move a profile toward the profile_100 award.
# - The FK is not ON DELETE CASCADE, matching 0055: DPDP erasure scrubs the
#   user row rather than deleting it, so the parent always survives. The
#   erasure path deletes this row explicitly instead.
# - Downgrade drops the table and the column; nothing else references either.

_LAND_UNITS = ("acres", "hectares")
_TENURES = ("owned", "leased", "both")
_IRRIGATION = ("borewell", "canal", "rainfed")


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column(
            "describes",
            sa.dialects.postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema="identity",
    )
    op.create_table(
        "farm_profiles",
        sa.Column(
            "id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.users.id"),
            nullable=False,
            unique=True,
        ),
        # numeric, not float: land is compared against per-hectare scheme
        # thresholds and 2.9999999 acres must not sit on the wrong side of one
        sa.Column("land_area", sa.Numeric(8, 2), nullable=True),
        sa.Column("land_unit", sa.Text(), nullable=True),
        sa.Column("tenure", sa.Text(), nullable=True),
        sa.Column("cattle", sa.Integer(), nullable=True),
        sa.Column("goats", sa.Integer(), nullable=True),
        sa.Column("poultry", sa.Integer(), nullable=True),
        sa.Column("irrigation", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Constraints in the DATABASE, not only in pydantic: these columns are
        # written by one router today, but a bad value would be read by every
        # vertical's advisories later, and a CHECK is the only guard that
        # survives a future writer that forgets to validate.
        sa.CheckConstraint(
            "land_unit IS NULL OR land_unit IN ('acres', 'hectares')",
            name="ck_identity_farm_profiles_land_unit",
        ),
        sa.CheckConstraint(
            "tenure IS NULL OR tenure IN ('owned', 'leased', 'both')",
            name="ck_identity_farm_profiles_tenure",
        ),
        sa.CheckConstraint(
            "irrigation IS NULL OR irrigation IN ('borewell', 'canal', 'rainfed')",
            name="ck_identity_farm_profiles_irrigation",
        ),
        sa.CheckConstraint(
            "land_area IS NULL OR land_area >= 0",
            name="ck_identity_farm_profiles_land_area",
        ),
        sa.CheckConstraint(
            "(cattle IS NULL OR cattle >= 0) AND (goats IS NULL OR goats >= 0)"
            " AND (poultry IS NULL OR poultry >= 0)",
            name="ck_identity_farm_profiles_livestock",
        ),
        schema="identity",
    )


def downgrade() -> None:
    op.drop_table("farm_profiles", schema="identity")
    op.drop_column("profiles", "describes", schema="identity")
