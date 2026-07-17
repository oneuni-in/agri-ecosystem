# backend/core/alembic/versions/0018_catalog_v1.py
"""D17 vertical registry + versioned spec-schemas + products (catalog E2 in
basic form, hosted in schema directory). Seeds the milk vertical, milk spec
schema v1, and the catalog_schema_admin flag (disabled).

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-17

"""
# -- THREAT/NOTES:
# downgrade data loss: drops products (all product listings + media keys),
#   spec_schemas (every version), vertical_registry, and the
#   catalog_schema_admin flag. Media objects in the bucket are NOT deleted
#   (orphaned keys - same accepted trade-off as D16 evidence docs).
# locks: CREATE TABLE/TYPE on empty objects, small seed inserts. Negligible.
# rollout: tables ship empty except seeds. 0013 default privileges give
#   app_rt blanket DML on new directory tables; spec_schemas then gets
#   UPDATE/DELETE REVOKED - schema versions are append-only BY GRANT
#   (a published version is pinned by products; changing it would corrupt
#   their rendering contract - publish version N+1 instead).
# schema-injection defence: fields JSONB is validated by
#   modules/directory/specs.parse_fields on every admin write; product specs
#   are validated against the pinned version on every write.

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, soft_delete_column, timestamp_columns, ugc_column

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)

vertical_status_enum = postgresql.ENUM(
    "active", "hidden", name="vertical_status", schema="directory", create_type=False
)
product_status_enum = postgresql.ENUM(
    "active", "archived", name="product_status", schema="directory", create_type=False
)

vertical_registry_table = sa.table(
    "vertical_registry",
    sa.column("id", _uuid),
    sa.column("slug", sa.Text),
    sa.column("name", postgresql.JSONB),
    sa.column("engines_enabled", postgresql.JSONB),
    sa.column("nav_placement", postgresql.JSONB),
    sa.column("status", vertical_status_enum),
    schema="directory",
)

spec_schemas_table = sa.table(
    "spec_schemas",
    sa.column("id", _uuid),
    sa.column("vertical_slug", sa.Text),
    sa.column("version", sa.Integer),
    sa.column("fields", postgresql.JSONB),
    schema="directory",
)

# milk spec schema v1 - three fields, exact contract modules/directory/specs.py validates against
MILK_SCHEMA_V1_FIELDS = [
    {
        "key": "milk_type",
        "label": {"en": "Milk type", "ta": "பால் வகை", "hi": "दूध का प्रकार"},
        "type": "enum",
        "options": ["cow", "buffalo", "a2", "toned", "organic"],
        "required": True,
        "filterable": True,
        "facet": True,
        "group": "basics",
    },
    {
        "key": "fat_percent",
        "label": {"en": "Fat %", "ta": "கொழுப்பு %", "hi": "वसा %"},
        "type": "number",
        "unit": "%",
        "min": 0,
        "max": 15,
        "filterable": True,
        "comparable": True,
        "group": "nutrition",
    },
    {
        "key": "pack_size",
        "label": {"en": "Pack size", "ta": "பேக் அளவு", "hi": "पैक आकार"},
        "type": "enum",
        "options": ["250ml", "500ml", "1l", "5l", "bulk"],
        "filterable": True,
        "facet": True,
        "group": "basics",
    },
]


def upgrade() -> None:
    bind = op.get_bind()
    sa.Enum("active", "hidden", name="vertical_status", schema="directory").create(
        bind, checkfirst=True
    )
    sa.Enum("active", "archived", name="product_status", schema="directory").create(
        bind, checkfirst=True
    )

    op.create_table(
        "vertical_registry",
        pk_column(),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        sa.Column("name", postgresql.JSONB, nullable=False),
        sa.Column("engines_enabled", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("nav_placement", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "status", vertical_status_enum, nullable=False, server_default=sa.text("'active'")
        ),
        *timestamp_columns(),
        schema="directory",
    )

    op.create_table(
        "spec_schemas",
        pk_column(),
        sa.Column(
            "vertical_slug",
            sa.Text,
            sa.ForeignKey("directory.vertical_registry.slug"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("fields", postgresql.JSONB, nullable=False),
        *timestamp_columns(),
        sa.UniqueConstraint(
            "vertical_slug", "version", name="uq_spec_schemas_vertical_slug_version"
        ),
        schema="directory",
    )

    op.create_table(
        "products",
        pk_column(),
        sa.Column(
            "business_id",
            _uuid,
            sa.ForeignKey("directory.businesses.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "vertical_slug",
            sa.Text,
            sa.ForeignKey("directory.vertical_registry.slug"),
            nullable=False,
            index=True,
        ),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("slug", sa.Text, nullable=False, unique=True, index=True),
        sa.Column("specs", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("price_display", sa.Text, nullable=True),
        sa.Column("media_keys", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "status", product_status_enum, nullable=False, server_default=sa.text("'active'")
        ),
        ugc_column(),
        soft_delete_column(),
        *timestamp_columns(),
        schema="directory",
    )
    # admin moderation queue paging
    op.create_index(
        "ix_directory_products_moderation_status_id",
        "products",
        ["moderation_status", "id"],
        schema="directory",
    )

    # 0013's default privileges already cover new directory tables; explicit
    # grant keeps the intended app_rt profile reviewable here (0016/0017 precedent).
    op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "directory" TO app_rt')
    # schema versions are append-only BY GRANT - see THREAT block above.
    op.execute("REVOKE UPDATE, DELETE ON directory.spec_schemas FROM app_rt")

    op.bulk_insert(
        vertical_registry_table,
        [
            {
                "id": uuid6.uuid7(),
                "slug": "milk",
                "name": {"en": "Milk", "ta": "பால்", "hi": "दूध"},
                "engines_enabled": {
                    "directory": True,
                    "catalog": True,
                    "reviews": True,
                    "leads": True,
                    "search": True,
                },
                "nav_placement": {"header": True, "order": 1},
                "status": "active",
            }
        ],
    )

    op.bulk_insert(
        spec_schemas_table,
        [
            {
                "id": uuid6.uuid7(),
                "vertical_slug": "milk",
                "version": 1,
                "fields": MILK_SCHEMA_V1_FIELDS,
            }
        ],
    )

    op.execute(
        "INSERT INTO public.feature_flags (key, enabled, description) VALUES "
        "('catalog_schema_admin', false, "
        "'Gates spec-schema version creation via /admin/catalog')"
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DELETE FROM public.feature_flags WHERE key = 'catalog_schema_admin'")
    op.drop_table("products", schema="directory")
    op.drop_table("spec_schemas", schema="directory")
    op.drop_table("vertical_registry", schema="directory")
    sa.Enum(name="product_status", schema="directory").drop(bind, checkfirst=True)
    sa.Enum(name="vertical_status", schema="directory").drop(bind, checkfirst=True)
