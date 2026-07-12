# backend/core/alembic/versions/0012_audit_v1.py
"""D12 audit: append-only tamper-evident audit log + restricted runtime role.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-12

"""
# -- THREAT/NOTES:
# downgrade data loss: drops audit.entries - the entire audit record for this
#   database. Acceptable pre-launch; in prod, archive the table first.
# locks: CREATE SCHEMA/TABLE/ROLE and GRANT take catalog locks only.
# rollout: app_rt is CLUSTER-wide; creation is idempotent because test/dev
#   databases are recreated against the same cluster. The dev/CI password is
#   'app_rt' (dev-only credentials, same standing as app/app); prod must
#   ALTER ROLE app_rt PASSWORD '<secret>' before flipping the runtime
#   DATABASE_URL to app_rt. Grants are per-database and re-run on every fresh
#   DB via this migration. Downgrade revokes grants and drops the role only
#   if no other database on the cluster still depends on it.

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# every schema from 0001 plus public (feature_flags lives there)
APP_SCHEMAS = (
    "identity",
    "coins",
    "directory",
    "leads",
    "content",
    "market",
    "ads",
    "notify",
    "billing",
    "geo",
    "public",
)


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "audit"')
    op.create_table(
        "entries",
        pk_column(),
        # no timestamp_columns(): append-only rows get created_at only, an
        # updated_at column on an immutable table would be a lie
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("target_type", sa.Text, nullable=True),
        sa.Column("target_id", sa.Text, nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("ip", sa.Text, nullable=True),
        sa.Column("chain_day", sa.Date, nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("prev_hash", sa.Text, nullable=False),
        sa.Column("entry_hash", sa.Text, nullable=False),
        sa.UniqueConstraint("chain_day", "seq"),
        schema="audit",
    )
    op.create_index(None, "entries", ["actor_user_id"], schema="audit")
    op.create_index(None, "entries", ["action"], schema="audit")

    # cluster-wide role: IF NOT EXISTS guard because test DBs are recreated
    # against the same cluster and this migration re-runs there
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_rt') THEN
                CREATE ROLE app_rt LOGIN NOSUPERUSER PASSWORD 'app_rt';
            END IF;
        END
        $$
        """
    )
    for schema in APP_SCHEMAS:
        op.execute(f'GRANT USAGE ON SCHEMA "{schema}" TO app_rt')
        op.execute(
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "{schema}" TO app_rt'
        )
        op.execute(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA "{schema}" TO app_rt')
        op.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" '
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rt"
        )
    # the non-negotiable: audit is INSERT+SELECT only for the runtime role
    op.execute('GRANT USAGE ON SCHEMA "audit" TO app_rt')
    op.execute("GRANT SELECT, INSERT ON audit.entries TO app_rt")
    op.execute(
        'ALTER DEFAULT PRIVILEGES IN SCHEMA "audit" GRANT SELECT, INSERT ON TABLES TO app_rt'
    )


def downgrade() -> None:
    for schema in (*APP_SCHEMAS, "audit"):
        op.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" REVOKE ALL ON TABLES FROM app_rt'
        )
        op.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA "{schema}" FROM app_rt')
        op.execute(f'REVOKE ALL ON ALL SEQUENCES IN SCHEMA "{schema}" FROM app_rt')
        op.execute(f'REVOKE ALL ON SCHEMA "{schema}" FROM app_rt')
    op.drop_table("entries", schema="audit")
    op.execute('DROP SCHEMA IF EXISTS "audit"')
    # the role may still hold grants in OTHER databases on this cluster
    op.execute(
        """
        DO $$
        BEGIN
            BEGIN
                DROP ROLE IF EXISTS app_rt;
            EXCEPTION WHEN dependent_objects_still_exist THEN
                NULL;
            END;
        END
        $$
        """
    )
