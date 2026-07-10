"""Enable pg_stat_statements for query observability.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-10

"""

# -- THREAT/NOTES:
# downgrade data loss: drops the extension and its accumulated statistics;
#   nothing application-facing reads them.
# locks: CREATE/DROP EXTENSION touches the catalog momentarily; negligible.
# rollout: querying the pg_stat_statements view needs the server started with
#   shared_preload_libraries=pg_stat_statements (docker-compose command), but
#   CREATE EXTENSION itself does not — CI's plain postgres:16 service applies
#   this revision cleanly.

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_stat_statements")
