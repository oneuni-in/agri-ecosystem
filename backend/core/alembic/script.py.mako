"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
# -- THREAT/NOTES:
# downgrade data loss: TODO what data a downgrade destroys, and why that is acceptable
# locks: TODO tables locked and expected duration at production scale
# rollout: TODO ordering constraints, backfills, feature flags
#
# The block above is mandatory: tests/test_lint_contracts.py fails while any
# TODO remains. Hand-written tables must include the standard mixin columns:
#   from shared.migrations import pk_column, timestamp_columns, soft_delete_column, ugc_column

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
