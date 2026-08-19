"""Phase 2: the education engine — five tables, SELECT-only for app_rt.

Revision ID: 0049
Revises: 0048
Create Date: 2026-08-18

The agri-colleges vertical's storage. Five tables in a new `education`
schema, mirroring the frozen CSV contract the D41 data track has validated
against since it was written: 772 institutions, 47 programmes, 277
offerings, 22 scholarships/exams and 13 guides arrive from a reviewed seed
commit through `scripts/import_education_seed.py`.

APP_RT GETS SELECT AND NOTHING ELSE, WHICH NO OTHER SCHEMA DOES.

0023/0027/0038/0045/0046/0048 all grant DML. This one does not, and the
difference is the design rather than an oversight. Nothing here is
user-writable: every row is reviewed in a PR before it exists, so write
access would be surface area with no use case behind it. Enabling CRUD
later is an explicit, reviewable grant change — which is the point.

STATE IS AN FK; DISTRICT IS NOT. THE ASYMMETRY IS DELIBERATE.

`state_id` is a real cross-schema FK to `geo.states.id`, as spec section 4
asks. All 36 states are in `data/geo/states.csv`, so the constraint can
never reject a valid row, and `geo.districts` already declares
`ForeignKey("geo.states.id")` — the cross-schema reference is the house
idiom, not a new risk.

`district_id` deliberately is not one. `data/geo/districts.csv` holds 38
rows, every one of them Tamil Nadu (state 33), until D65. An FK there would
reject a valid Punjab college outright. It holds the district's LGD code as
a plain integer instead, and reads join on `District.lgd_code`. District
filtering therefore resolves inside Tamil Nadu only until the rest of the
geo data lands.

WHY THERE ARE NO ENUM TYPES.

`kind`, `trust`, `status`, `level`, `discipline`, `category` and `scope` are
all Text. `scripts/education_seed_contract.py` rejects a bad value for every
one of them before the importer sees it, and it is the single source of
validation truth that both CI and the importer run. A PG enum would put a
second, weaker copy of those lists in the database, and widening one later
means an ALTER TYPE in a migration instead of a line in a reviewed contract.

FEES ARE INTEGER, THOUGH SPEC SECTION 4 SAYS NUMERIC.

Every one of the 277 fee values in the seed is whole rupees; nobody quotes
paise in an annual fee. Numeric would put a Decimal on the wire, which the
D24 covers work already had to serialize as a string to stop it arriving as
a float. An int is exact, JSON-native and needs no convention.
"""

# -- THREAT/NOTES:
# - New `education` schema and five new tables. No existing table is touched,
#   so nothing is rewritten and no existing query plan changes.
# - GRANTs: SELECT ONLY to app_rt, unlike every other schema in this tree.
#   The application cannot write college data; the importer runs as the
#   migration/table-owner role. This is both a security property and the
#   cleanest expression of D4.
# - Two cross-schema FKs into `geo.states` (institutions, guides), both
#   ON DELETE RESTRICT. geo.districts already FKs across schemas the same
#   way, so this introduces no new pattern. RESTRICT rather than CASCADE:
#   deleting a state out from under 772 colleges should fail loudly.
# - Self-FKs on institutions (parent_id, merged_into_id), both RESTRICT, so
#   a merge target cannot be deleted while something still points at it.
# - locks: CREATE SCHEMA / CREATE TABLE / CREATE INDEX / GRANT take catalog
#   locks only. Nothing here blocks a running app.
# - downgrade drops the schema and all five tables. The rows are entirely
#   reproducible from the committed CSV bundle by rerunning the importer,
#   so this is not data loss in the way dropping a user table would be.
# - No PII. Institutions are public records: names, addresses and office
#   phone numbers already printed on official sites and in AISHE.
# - No moderation state, because there is no user-generated row to moderate.
#   Editing a college means editing a CSV and opening a PR.
# - No new enum type, no new role.

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "education"

_TABLES = (
    "guides",
    "student_resources",
    "institution_programmes",
    "programmes",
    "institutions",
)


def upgrade() -> None:
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')

    op.create_table(
        "institutions",
        pk_column(),
        *timestamp_columns(),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("name_ta", sa.Text()),
        sa.Column("name_hi", sa.Text()),
        sa.Column("short_name", sa.Text()),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("is_government", sa.Boolean()),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.institutions.id", ondelete="RESTRICT"),
        ),
        sa.Column("country_code", sa.Text(), nullable=False, server_default="IN"),
        sa.Column(
            "state_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("geo.states.id", ondelete="RESTRICT"),
        ),
        # LGD code, NOT an FK -- see the module docstring.
        sa.Column("district_id", sa.Integer()),
        sa.Column("pincode", sa.Text()),
        sa.Column("lat", sa.Numeric(9, 6)),
        sa.Column("lng", sa.Numeric(9, 6)),
        sa.Column("address", sa.Text()),
        sa.Column("website", sa.Text()),
        sa.Column("contact_phone", sa.Text()),
        sa.Column("contact_email", sa.Text()),
        sa.Column("established_year", sa.Integer()),
        sa.Column("accreditation", postgresql.JSONB()),
        sa.Column("trust", sa.Text(), nullable=False, server_default="listed"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column(
            "merged_into_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.institutions.id", ondelete="RESTRICT"),
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("last_verified_at", sa.Date(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_education_institutions_slug"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_education_institutions_state_id", "institutions", ["state_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_education_institutions_district_id", "institutions", ["district_id"], schema=SCHEMA
    )
    # /colleges filters on these together; the ISR state pages filter on
    # state_id alone, which the index above already serves as a prefix.
    op.create_index(
        "ix_education_institutions_state_trust_status",
        "institutions",
        ["state_id", "trust", "status"],
        schema=SCHEMA,
    )

    op.create_table(
        "programmes",
        pk_column(),
        *timestamp_columns(),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("name_ta", sa.Text()),
        sa.Column("name_hi", sa.Text()),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("discipline", sa.Text(), nullable=False),
        sa.Column("duration_months", sa.Integer()),
        sa.Column("description_en", sa.Text()),
        sa.Column("description_ta", sa.Text()),
        sa.Column("description_hi", sa.Text()),
        sa.UniqueConstraint("slug", name="uq_education_programmes_slug"),
        schema=SCHEMA,
    )

    op.create_table(
        "institution_programmes",
        pk_column(),
        *timestamp_columns(),
        sa.Column(
            "institution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.institutions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "programme_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.programmes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("intake_seats", sa.Integer()),
        sa.Column("annual_fees_inr", sa.Integer()),
        sa.Column("fee_note", sa.Text()),
        sa.Column("admission_route", sa.Text()),
        # Its OWN stamps, separate from the institution's, so a page can say
        # "college verified Mar 2026 · fees last checked Aug 2025" honestly.
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("last_verified_at", sa.Date(), nullable=False),
        sa.UniqueConstraint("institution_id", "programme_id", name="uq_inst_prog"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_education_inst_prog_programme_id",
        "institution_programmes",
        ["programme_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "student_resources",
        pk_column(),
        *timestamp_columns(),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("name_ta", sa.Text()),
        sa.Column("name_hi", sa.Text()),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("category", sa.Text()),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text()),
        sa.Column("levels", sa.Text()),
        sa.Column("eligibility_en", sa.Text()),
        sa.Column("eligibility_ta", sa.Text()),
        sa.Column("eligibility_hi", sa.Text()),
        sa.Column("benefit", sa.Text()),
        sa.Column("applies_to", postgresql.JSONB()),
        sa.Column("window", postgresql.JSONB()),
        sa.Column("official_url", sa.Text(), nullable=False),
        sa.Column("last_verified_at", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.UniqueConstraint("slug", name="uq_education_student_resources_slug"),
        schema=SCHEMA,
    )

    op.create_table(
        "guides",
        pk_column(),
        *timestamp_columns(),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("title_en", sa.Text(), nullable=False),
        sa.Column("title_ta", sa.Text()),
        sa.Column("title_hi", sa.Text()),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("country_code", sa.Text()),
        sa.Column(
            "state_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("geo.states.id", ondelete="RESTRICT"),
        ),
        sa.Column("summary_en", sa.Text()),
        sa.Column("summary_ta", sa.Text()),
        sa.Column("summary_hi", sa.Text()),
        sa.Column("steps", postgresql.JSONB()),
        sa.Column("official_links", postgresql.JSONB()),
        sa.Column("last_verified_at", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.UniqueConstraint("slug", name="uq_education_guides_slug"),
        schema=SCHEMA,
    )

    # SELECT and nothing else. Read the module docstring before widening this.
    op.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO app_rt")
    for table in _TABLES:
        op.execute(f"GRANT SELECT ON {SCHEMA}.{table} TO app_rt")


def downgrade() -> None:
    for table in _TABLES:
        op.drop_table(table, schema=SCHEMA)
    op.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}"')
