# backend/core/alembic/versions/0054_audit_entries_immutable.py
"""audit.entries refuses UPDATE and DELETE from everyone, owner included.

0013 protected the audit log with a grant: app_rt holds SELECT and INSERT and
nothing else, so the application cannot rewrite history. That is the right
first line, and it is not the whole line - a grant binds the runtime role, and
the role a compromise of the MIGRATION credentials gets you is the owner,
which grants do not constrain at all.

Every sibling append-only table already closed that: coins.ledger_entries
(0012), billing.ledger_entries (0034), ads.impressions/clicks (0022),
ads.delivery_decisions (0031), geo.pincode_tier_history (0032). Each has a
BEFORE UPDATE OR DELETE trigger that raises regardless of who is connected.
The audit log - the table whose entire job is to be the record of what
happened - was the one holding out.

DETECTION ALREADY WORKED; THIS IS PREVENTION

shared/audit.py chains each row's hash to its predecessor, and
tests/test_audit_integrity.py proves a tampered row surfaces as hash_mismatch
and a removed one as seq_gap. That stays true and stays valuable: a trigger
can be disabled by the owner, so the chain remains the thing that notices.
The difference is that rewriting history is no longer a plain UPDATE - it now
takes a DDL statement someone has to decide to run, and the tests that
simulate a compromised owner have been changed to take exactly that step, so
the cost is visible in the diff.

TRIGGER, NOT A REVOKE FROM THE OWNER

Revoking from the owner does not work in Postgres: the owner can re-grant to
itself at will, so it is a speed bump rather than a control. A trigger applies
to every role. `REVOKE ... FROM PUBLIC` is included as well, matching 0012.
"""

# -- THREAT/NOTES:
# - No schema change: no column, index or constraint is touched. A trigger and
#   a function are added, so no row is rewritten and no query plan changes.
# - locks: CREATE FUNCTION is catalog-only; CREATE TRIGGER takes a brief
#   ACCESS EXCLUSIVE on audit.entries. The table is append-only and INSERTs are
#   short, so the wait is bounded by an in-flight insert, not by a scan.
# - INSERT is deliberately untouched. The trigger is BEFORE UPDATE OR DELETE
#   only: writing new audit rows is the entire point of the table.
# - Blast radius if wrong: any legitimate UPDATE/DELETE on audit.entries starts
#   raising. There is none - app_rt has never held those grants, and nothing in
#   modules/, shared/ or scripts/ issues one. Reversible via the downgrade.
# - Data-retention note: a future purge job (DPDP erasure, retention window)
#   will hit this and should. Purging the audit log is exactly the operation
#   that deserves a deliberate, reviewed path rather than a DELETE.
# - No PII, no new role, no enum, no data migration, no grant change for app_rt
#   (0013's SELECT+INSERT still stands).

from collections.abc import Sequence

from alembic import op

revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRIGGER = "audit_entries_immutable"


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit.reject_entry_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit.entries is append-only (% blocked)', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$;
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {TRIGGER}
        BEFORE UPDATE OR DELETE ON audit.entries
        FOR EACH ROW EXECUTE FUNCTION audit.reject_entry_mutation();
        """
    )
    op.execute("REVOKE UPDATE, DELETE ON audit.entries FROM PUBLIC")


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {TRIGGER} ON audit.entries")
    op.execute("DROP FUNCTION IF EXISTS audit.reject_entry_mutation()")
