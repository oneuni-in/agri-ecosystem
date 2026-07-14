# backend/core/alembic/versions/0015_coins_harden_app_rt.py
"""D13 coins: harden ledger immutability against the app_rt runtime role
introduced by D12 (0013_audit_v1). That migration grants blanket
SELECT/INSERT/UPDATE/DELETE to app_rt across every application schema,
including coins - re-opening grant-level UPDATE/DELETE access to
coins.ledger_entries that 0012_coins_v1 had revoked from the old `app` role.
The BEFORE UPDATE/DELETE trigger added in 0012_coins_v1 is the real,
role-independent guarantee (it fires for every role, including the table
owner) and already blocks any mutation regardless of grants; this migration
restores the grant-level defense-in-depth to match the connecting role that
D12 made current (`app_rt`), so the privilege list matches the design intent.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-14

"""
# -- THREAT/NOTES:
# downgrade data loss: none - re-grants UPDATE, DELETE on coins.ledger_entries
#   to app_rt, restoring the state 0013_audit_v1's blanket per-schema grant
#   already left it in. The trigger remains the real guarantee either way, so
#   downgrading this migration does not reopen a functional immutability gap.
# locks: single-table REVOKE/GRANT; catalog lock only, no rows affected.
# rollout: must run after 0013 (creates app_rt and grants it UPDATE/DELETE
#   across every schema, including coins) and after 0012 (creates
#   coins.ledger_entries). REVOKE/GRANT on a privilege the role already
#   holds/lacks is a no-op in Postgres, so this is safe to run more than once.

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("REVOKE UPDATE, DELETE ON coins.ledger_entries FROM app_rt")


def downgrade() -> None:
    op.execute("GRANT UPDATE, DELETE ON coins.ledger_entries TO app_rt")
