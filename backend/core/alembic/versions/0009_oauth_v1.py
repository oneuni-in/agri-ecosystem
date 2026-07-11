"""oauth v1: client registry + one-time authorization codes, seeded clients.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-11

"""
# -- THREAT/NOTES:
# downgrade data loss: drops both oauth tables - the seeded client registry and
#   every authorization code. Codes live 60 seconds, so their loss is noise;
#   re-upgrading reseeds the registry identically. Safe pre-launch.
# locks: CREATE/DROP TABLE on empty tables plus four INSERTs; negligible.
# rollout: run after 0008. The registry is SEED-ONLY by design (threat model:
#   malicious client registration) - no registration endpoint exists, so adding
#   or changing a client or redirect URI is always a reviewed migration.
# environment split: redirect URIs are exact-match, so dev's localhost URIs
#   must never be valid in production. The seed resolves the environment via
#   settings.get_settings().app_env (env var or .env, exactly like the app):
#   prod seeds only https production callbacks, everything else seeds only
#   localhost callbacks. Staging URIs land in a later migration when staging
#   exists (owner-driven).

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op
from settings import get_settings
from shared.migrations import pk_column, timestamp_columns

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# dev ports per D01-A: milk 3000, organic 3001, agri 3002, id 3003, admin 3004
# (id.agri.in itself is the server, never a client). Callback path is the
# D10 BFF route handler.
_DEV_URIS: dict[str, list[str]] = {
    "web-agri": ["http://localhost:3002/api/auth/callback"],
    "web-milk": ["http://localhost:3000/api/auth/callback"],
    "web-organic": ["http://localhost:3001/api/auth/callback"],
    "web-admin": ["http://localhost:3004/api/auth/callback"],
}

_PROD_URIS: dict[str, list[str]] = {
    "web-agri": ["https://agri.in/api/auth/callback"],
    "web-milk": ["https://milk.in/api/auth/callback"],
    "web-organic": ["https://organicstore.in/api/auth/callback"],
    "web-admin": ["https://admin.agri.in/api/auth/callback"],
}

_CLIENT_NAMES: dict[str, str] = {
    "web-agri": "agri.in web app",
    "web-milk": "milk.in web app",
    "web-organic": "organicstore.in web app",
    "web-admin": "admin web app",
}

_uuid = postgresql.UUID(as_uuid=True)
clients_table = sa.table(
    "oauth_clients",
    sa.column("id", _uuid),
    sa.column("client_id", sa.Text),
    sa.column("client_name", sa.Text),
    sa.column("redirect_uris", postgresql.JSONB),
    schema="identity",
)


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        pk_column(),
        *timestamp_columns(),
        sa.Column("client_id", sa.Text, nullable=False, unique=True),
        sa.Column("client_name", sa.Text, nullable=False),
        sa.Column("redirect_uris", postgresql.JSONB, nullable=False),
        schema="identity",
    )
    op.create_table(
        "oauth_codes",
        pk_column(),
        *timestamp_columns(),
        # hash-only, like otp_requests.code_hash: a DB dump must not yield
        # exchangeable codes. There is deliberately no plaintext column.
        sa.Column("code_hash", sa.Text, nullable=False, unique=True),
        sa.Column(
            "client_id",
            _uuid,
            sa.ForeignKey("identity.oauth_clients.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            _uuid,
            sa.ForeignKey("identity.users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("redirect_uri", sa.Text, nullable=False),
        sa.Column("code_challenge", sa.Text, nullable=False),
        sa.Column(
            "code_challenge_method", sa.Text, server_default=sa.text("'S256'"), nullable=False
        ),
        sa.Column("scope", sa.Text, server_default=sa.text("''"), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="identity",
    )

    uris = _PROD_URIS if get_settings().app_env == "prod" else _DEV_URIS
    op.bulk_insert(
        clients_table,
        [
            {
                "id": uuid6.uuid7(),
                "client_id": client_id,
                "client_name": _CLIENT_NAMES[client_id],
                "redirect_uris": client_uris,
            }
            for client_id, client_uris in uris.items()
        ],
    )


def downgrade() -> None:
    op.drop_table("oauth_codes", schema="identity")
    op.drop_table("oauth_clients", schema="identity")
