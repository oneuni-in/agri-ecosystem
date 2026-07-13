"""D13 coins: append-only AgriCoins ledger, derived balances, rules engine,
referrals, abuse flags. AgriCoins are NOT money: not purchasable, not
cashable, not transferable - there is deliberately no money/transfer column.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-13

"""
# -- THREAT/NOTES:
# downgrade data loss: drops the entire coins schema - every ledger entry,
#   balance, rule, referral and abuse flag is destroyed, and the three coins
#   permissions + their grants and the two feature flags are removed.
#   Acceptable pre-launch; post-launch a downgrade is an incident decision.
# immutability: ledger rows are protected by a BEFORE UPDATE/DELETE trigger
#   that RAISEs (holds even against the table owner) plus REVOKE UPDATE,DELETE
#   from the app role for defense in depth. The trigger is the real guarantee
#   because the app both owns and connects as one role.
# locks: CREATE TABLE / CREATE TYPE / CREATE TRIGGER on empty objects;
#   single-row DML on tiny RBAC/flag tables. Negligible pre-launch.
# rollout: tables ship empty except seeded rules/permissions/flags. The D13
#   service, worker and API are the only writers; deploy migration with code.

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)

# Sprint-1 rules (code, amount, daily_cap, weekly_cap, total_cap). A total_cap
# of 1 is the "once" rules; daily_cap 1 is daily_visit. Caps whose enforcement
# is a deterministic idempotency key are still recorded here for documentation
# and future non-deterministic rules.
SEED_RULES = [
    ("signup_complete", 100, None, None, 1),
    ("profile_100", 200, None, None, 1),
    ("daily_visit", 5, 1, None, None),
    ("referral_referrer", 250, None, None, None),
    ("referral_referee", 100, None, None, 1),
]

COINS_PERMISSIONS = [
    ("coins.rules.write", "create/update coins reward rules (admin)"),
    ("coins.adjust", "manually adjust a user's coin balance (admin)"),
    ("coins.abuse.review", "review and void referral abuse flags (admin)"),
]
# permission -> roles it is granted to
PERMISSION_GRANTS = {
    "coins.rules.write": ("super_admin",),
    "coins.adjust": ("super_admin",),
    "coins.abuse.review": ("super_admin", "staff"),
}

FEATURE_FLAGS = [
    ("coins_enabled", "master switch for AgriCoins awards/redeems"),
    ("coins_rules_admin", "expose the admin rules-CRUD surface"),
]

permissions_table = sa.table(
    "permissions",
    sa.column("id", _uuid),
    sa.column("name", sa.Text),
    sa.column("description", sa.Text),
    schema="identity",
)
roles_table = sa.table(
    "roles", sa.column("id", _uuid), sa.column("name", sa.Text), schema="identity"
)
role_permissions_table = sa.table(
    "role_permissions",
    sa.column("id", _uuid),
    sa.column("role_id", _uuid),
    sa.column("permission_id", _uuid),
    schema="identity",
)
feature_flags_table = sa.table(
    "feature_flags",
    sa.column("key", sa.Text),
    sa.column("enabled", sa.Boolean),
    sa.column("description", sa.Text),
    schema="public",
)


def upgrade() -> None:
    bind = op.get_bind()
    op.execute('CREATE SCHEMA IF NOT EXISTS "coins"')

    sa.Enum("pending", "rewarded", "voided", name="referral_status", schema="coins").create(
        bind, checkfirst=True
    )
    sa.Enum("open", "reviewed", "voided", name="abuse_status", schema="coins").create(
        bind, checkfirst=True
    )

    op.create_table(
        "ledger_entries",
        pk_column(),
        sa.Column("user_id", _uuid, nullable=False),
        sa.Column("delta", sa.BigInteger, nullable=False),
        sa.Column("reason_code", sa.Text, nullable=False),
        sa.Column("ref_type", sa.Text, nullable=False),
        sa.Column("ref_id", sa.Text, nullable=True),
        sa.Column("idempotency_key", sa.Text, nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("delta <> 0", name="delta_nonzero"),
        schema="coins",
    )
    op.create_index(
        "ix_coins_ledger_entries_user_id_id", "ledger_entries", ["user_id", "id"], schema="coins"
    )

    op.create_table(
        "balances",
        sa.Column("user_id", _uuid, primary_key=True),
        sa.Column("balance", sa.BigInteger, nullable=False, server_default="0"),
        *timestamp_columns(),
        sa.CheckConstraint("balance >= 0", name="balance_nonnegative"),
        schema="coins",
    )

    op.create_table(
        "rules",
        sa.Column("code", sa.Text, primary_key=True),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("daily_cap", sa.Integer, nullable=True),
        sa.Column("weekly_cap", sa.Integer, nullable=True),
        sa.Column("total_cap", sa.Integer, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("valid_from", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("valid_to", sa.TIMESTAMP(timezone=True), nullable=True),
        *timestamp_columns(),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
        schema="coins",
    )

    op.create_table(
        "referral_codes",
        sa.Column("user_id", _uuid, primary_key=True),
        sa.Column("code", sa.Text, nullable=False, unique=True),
        *timestamp_columns(),
        schema="coins",
    )

    op.create_table(
        "referrals",
        pk_column(),
        sa.Column("referrer_id", _uuid, nullable=False, index=True),
        sa.Column("referee_id", _uuid, nullable=False, unique=True),
        sa.Column("code", sa.Text, nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="referral_status", schema="coins", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("device_fingerprint", sa.Text, nullable=True),
        sa.Column("phone_prefix", sa.Text, nullable=True),
        *timestamp_columns(),
        sa.Column("rewarded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("voided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        schema="coins",
    )

    op.create_table(
        "abuse_flags",
        pk_column(),
        sa.Column(
            "referral_id", _uuid, sa.ForeignKey("coins.referrals.id"), nullable=False, index=True
        ),
        sa.Column("cluster_reason", sa.Text, nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="abuse_status", schema="coins", create_type=False),
            nullable=False,
            server_default="open",
        ),
        sa.Column("details", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("reviewed_by", _uuid, nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        *timestamp_columns(),
        schema="coins",
    )

    # Immutability: trigger holds even against the owner; REVOKE is belt-and-braces.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION coins.reject_ledger_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'coins.ledger_entries is append-only (% blocked)', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER coins_ledger_immutable
        BEFORE UPDATE OR DELETE ON coins.ledger_entries
        FOR EACH ROW EXECUTE FUNCTION coins.reject_ledger_mutation();
        """
    )
    op.execute("REVOKE UPDATE, DELETE ON coins.ledger_entries FROM PUBLIC")
    # app is the connecting role in every environment (settings.database_url).
    op.execute("REVOKE UPDATE, DELETE ON coins.ledger_entries FROM app")

    op.bulk_insert(
        sa.table(
            "rules",
            sa.column("code", sa.Text),
            sa.column("amount", sa.BigInteger),
            sa.column("daily_cap", sa.Integer),
            sa.column("weekly_cap", sa.Integer),
            sa.column("total_cap", sa.Integer),
            schema="coins",
        ),
        [
            {"code": c, "amount": a, "daily_cap": d, "weekly_cap": w, "total_cap": t}
            for (c, a, d, w, t) in SEED_RULES
        ],
    )

    # Permissions + grants (mirrors 0011 pattern).
    perm_rows = [{"id": uuid6.uuid7(), "name": n, "description": d} for (n, d) in COINS_PERMISSIONS]
    op.bulk_insert(permissions_table, perm_rows)
    perm_id = {r["name"]: r["id"] for r in perm_rows}
    roles = {
        name: rid
        for rid, name in bind.execute(sa.select(roles_table.c.id, roles_table.c.name)).all()
    }
    grants = [
        {"id": uuid6.uuid7(), "role_id": roles[role], "permission_id": perm_id[perm]}
        for perm, role_names in PERMISSION_GRANTS.items()
        for role in role_names
        if role in roles
    ]
    if grants:
        op.bulk_insert(role_permissions_table, grants)

    op.bulk_insert(
        feature_flags_table,
        [{"key": k, "enabled": False, "description": d} for (k, d) in FEATURE_FLAGS],
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(
        sa.delete(feature_flags_table).where(
            feature_flags_table.c.key.in_([k for k, _ in FEATURE_FLAGS])
        )
    )
    perm_ids = [
        pid
        for (pid,) in bind.execute(
            sa.select(permissions_table.c.id).where(
                permissions_table.c.name.in_([n for n, _ in COINS_PERMISSIONS])
            )
        ).all()
    ]
    if perm_ids:
        op.execute(
            sa.delete(role_permissions_table).where(
                role_permissions_table.c.permission_id.in_(perm_ids)
            )
        )
        op.execute(sa.delete(permissions_table).where(permissions_table.c.id.in_(perm_ids)))
    op.execute('DROP SCHEMA IF EXISTS "coins" CASCADE')
