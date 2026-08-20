# backend/core/alembic/versions/0055_more_reference_tables_readonly.py
"""Four more reference tables read-only; coins.rules keeps UPDATE and nothing else.

Continues 0051 (RBAC catalog) and 0053 (first five reference tables) in
unwinding 0013's blanket `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES`
across eleven schemas.

READ BY HAND, AGAIN, AND HERE IS WHY THAT KEEPS MATTERING

0053 recorded that a script matching `Model(` had cleared ads.impressions,
which is written via `model = Impression if kind == "imp" else Click` - a
class bound to a variable. This batch turned up the second shape:

    rule = await session.get(Rule, code)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(rule, field, value)
    await session.flush()

`coins.rules` is written by `PUT /admin/coins/rules/{code}`, and nothing
matching `Rule(`, `insert(Rule)` or `update(Rule)` appears anywhere. Load,
mutate, flush. Two different invisible-to-grep write shapes in two batches is
the argument against ever sweeping this table by pattern.

So coins.rules keeps UPDATE. It loses INSERT and DELETE, which are genuinely
unused: there is no POST or DELETE route for rules and the rows are seeded by
migration.

THE FOUR THAT ARE ACTUALLY READ-ONLY

directory.categories, identity.oauth_clients, market.commodities and
content.sources. Every prod mention was read - 24, 20, 15 and 10 of them -
and all are joins, type annotations, imports or comments. No construction, no
session.get-then-mutate, no bulk insert, no raw SQL. scripts/ was read too,
because those connect with settings.database_url (app_rt), not as the owner:
content_approve.py only reads Source to filter ContentItems by source_id.

Their rows arrive from migrations (seeded categories, the env-conditional
OAuth client seed, the curated commodity list, the content source list), all
of which run as the owner and are unaffected.

STILL GRANTED, AND WHY

identity.emails is read-only today but is user data with a verified_at column;
a verification flow would want the grant straight back, and churning the test
that seeds it buys little. The remaining ~90 tables are genuinely written.
"""

# -- THREAT/NOTES:
# - No schema change. Privileges only: no row rewritten, no query plan changed.
# - locks: REVOKE takes a catalog lock per table. Five short locks.
# - Blast radius if wrong: a needed write starts failing loudly with
#   `permission denied` rather than corrupting anything, and the downgrade
#   restores exactly what 0013 granted.
# - Seeding unaffected: these rows come from migrations, which run as owner.
# - coins.rules deliberately RETAINS UPDATE - see the docstring. Revoking it
#   would break the coins rules admin screen.
# - 0013's ALTER DEFAULT PRIVILEGES is still left alone: it governs tables
#   created later, which is right for the rest of these schemas. A new
#   reference table therefore inherits DML and needs adding to
#   tests/test_reference_table_grants.py, which asserts per table.
# - No PII, no new role, no enum, no data migration.

from collections.abc import Sequence

from alembic import op

revision: str = "0055"
down_revision: str | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# seeded by migration, only ever SELECTed at runtime
READ_ONLY_TABLES = (
    ("directory", "categories"),
    ("identity", "oauth_clients"),
    ("market", "commodities"),
    ("content", "sources"),
)

# written at runtime, but by exactly one UPDATE route
UPDATE_ONLY_TABLES = (("coins", "rules"),)


def upgrade() -> None:
    for schema, table in READ_ONLY_TABLES:
        op.execute(f"REVOKE INSERT, UPDATE, DELETE ON {schema}.{table} FROM app_rt")
    for schema, table in UPDATE_ONLY_TABLES:
        op.execute(f"REVOKE INSERT, DELETE ON {schema}.{table} FROM app_rt")


def downgrade() -> None:
    for schema, table in READ_ONLY_TABLES:
        op.execute(f"GRANT INSERT, UPDATE, DELETE ON {schema}.{table} TO app_rt")
    for schema, table in UPDATE_ONLY_TABLES:
        op.execute(f"GRANT INSERT, DELETE ON {schema}.{table} TO app_rt")
