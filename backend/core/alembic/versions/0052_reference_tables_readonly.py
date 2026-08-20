# backend/core/alembic/versions/0052_reference_tables_readonly.py
"""Five reference tables stop being writable by the runtime role.

0013 granted app_rt SELECT/INSERT/UPDATE/DELETE on every table across eleven
schemas. 0051 took the RBAC catalog back because leaving it writable let a
compromised process rewrite the permission matrix. This is the next slice of
the same debt: tables whose rows arrive from a migration and are only ever
read at runtime, so the write grant has no caller to serve.

WHY THIS SLICE IS SMALL, AND NOT A SWEEP

The first pass was mechanical - a script matching `Model(`, `insert(Model)`
and friends across modules/, shared/ and scripts/. It reported ads.impressions
as having no writer. It has one: modules/ads/router.py::_track does

    model = Impression if kind == "imp" else Click
    session.add(model(...))

which binds the class to a variable first, so no pattern for `Impression(`
can see it. Acting on that output would have revoked the ads beacon's INSERT
and taken impression tracking down in production, silently until the first
beacon fired.

So the script was demoted to a candidate finder and every table below was read
by hand. scripts/ counts as a caller here, not just modules/: those connect
with settings.database_url, which is app_rt, so a seed script writing one of
these would break the same way. None does - `grep -E "\\b(Address|CropCalendar|
Msp|Scheme|Template)\\b" scripts/*.py` is empty.

Left for a later pass, because being unread is not the same as being
read-only: directory.categories (24 prod mentions), identity.oauth_clients
(20), market.commodities (15), coins.rules (13), content.sources.
identity.emails is read-only today but is user data with a verified_at column,
so a verification flow would want the grant straight back.
"""

# -- THREAT/NOTES:
# - No schema change: no table created, altered or dropped. Privileges only,
#   so no row is rewritten and no query plan changes.
# - locks: REVOKE takes a catalog lock per table. Five short locks, no data
#   pages touched, safe against a running app.
# - Blast radius if wrong: the API loses a write it needs, and it fails loudly
#   with `permission denied` rather than corrupting anything. Reversible via
#   the downgrade, which restores exactly what 0013 granted.
# - Seeding is unaffected: these rows arrive from migrations, which run as the
#   OWNER (app), not as app_rt.
# - 0013's ALTER DEFAULT PRIVILEGES is left alone deliberately - it governs
#   tables created later, which is right for the rest of these schemas. The
#   consequence is that a new reference table inherits DML and needs the same
#   revoke; tests/test_reference_table_grants.py asserts per table rather than
#   trusting the default, so that shows up as a failing test.
# - No PII, no new role, no enum, no data migration.

from collections.abc import Sequence

from alembic import op

revision: str = "0052"
down_revision: str | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (schema, table) seeded by migration, only ever SELECTed at runtime
READ_ONLY_TABLES = (
    ("identity", "addresses"),
    ("market", "crop_calendars"),
    ("market", "msp"),
    ("market", "schemes"),
    ("notify", "templates"),
)


def upgrade() -> None:
    for schema, table in READ_ONLY_TABLES:
        op.execute(f"REVOKE INSERT, UPDATE, DELETE ON {schema}.{table} FROM app_rt")


def downgrade() -> None:
    for schema, table in READ_ONLY_TABLES:
        op.execute(f"GRANT INSERT, UPDATE, DELETE ON {schema}.{table} TO app_rt")
