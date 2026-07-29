# backend/core/alembic/versions/0028_signup_gate.py
"""Signup gate flag (D30.B).

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-28

"""
# -- THREAT/NOTES:
# - Seeds ENABLED, unlike notify.push_enabled / billing_enabled which seed
#   false. shared/flags.py fails CLOSED on unknown keys, so an absent row means
#   signup_allowed() refuses every OTP request - in dev and CI too, which takes
#   the D29 e2e suites (15+ specs drive real OTP login) down with it. The
#   default therefore has to be open, and the launch gate is applied by flipping
#   this row to false in production.
# - Seeding true does NOT risk launching signup on the mock driver: the
#   prod-on-mock invariant in modules/identity/signup_gate.py refuses regardless
#   of this value. That is exactly why the invariant exists rather than relying
#   on flag discipline.
# - No table, no grants, no enum: one row in an existing table.
# - Reversible: downgrade deletes the row. Re-upgrade re-inserts it, so
#   migrate_check's up/down/up stays green (ON CONFLICT DO NOTHING).

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO public.feature_flags (key, enabled, description) "
            "VALUES ('signup_enabled', true, "
            "'D30: OTP issuance for signup+login; flipped false in prod until DLT approval') "
            "ON CONFLICT (key) DO NOTHING"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM public.feature_flags WHERE key = 'signup_enabled'"))
