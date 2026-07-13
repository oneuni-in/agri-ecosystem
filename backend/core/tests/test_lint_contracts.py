"""Repo-wide lint contracts that ruff cannot express: the THREAT/NOTES block
is mandatory in every migration, and OFFSET pagination is banned everywhere
(D03 non-negotiable 3 - keyset paginate() is the only list mechanism)."""

from pathlib import Path

from tests.lint_checks import check_ledger_writes, check_offset_ban

CORE = Path(__file__).resolve().parents[1]
VERSIONS = CORE / "alembic" / "versions"
BANNED_SCOPE = [CORE / "main.py", CORE / "settings.py", CORE / "modules", CORE / "shared", VERSIONS]

# coins.service is the sanctioned writer. models.py is allowlisted because the
# regex `LedgerEntry\s*\(` also matches the `class LedgerEntry(...)` definition.
LEDGER_ALLOWED = {
    CORE / "modules" / "coins" / "service.py",
    CORE / "modules" / "coins" / "models.py",
}


def test_every_migration_has_a_filled_threat_notes_block() -> None:
    migrations = sorted(VERSIONS.glob("*.py"))
    assert migrations, "no migrations found - wrong path?"
    for migration in migrations:
        text = migration.read_text(encoding="utf-8")
        assert "-- THREAT/NOTES:" in text, f"{migration.name}: missing THREAT/NOTES block"
        assert "TODO" not in text, f"{migration.name}: THREAT/NOTES block not filled in"


def test_template_generates_the_threat_notes_block() -> None:
    template = (CORE / "alembic" / "script.py.mako").read_text(encoding="utf-8")
    assert "-- THREAT/NOTES:" in template


def test_offset_ban_fires_on_fixture() -> None:
    fixture = Path(__file__).parent / "fixtures" / "offset_violation.py.txt"
    violations = check_offset_ban([fixture])
    # one .offset( call and one raw-SQL OFFSET, with file:line locations
    assert len(violations) == 2
    assert all("offset_violation.py.txt:" in violation for violation in violations)


def test_offset_ban_ignores_clean_code() -> None:
    clean = Path(__file__).resolve()  # this file mentions offset only in strings/names
    assert check_offset_ban([CORE / "shared" / "pagination.py"]) == []
    assert clean.exists()


def test_no_offset_pagination_anywhere_in_app_code() -> None:
    violations = check_offset_ban(BANNED_SCOPE)
    assert violations == [], "OFFSET pagination is banned; use shared.pagination.paginate:\n" + (
        "\n".join(violations)
    )


def test_ledger_write_ban_fires_on_fixture() -> None:
    fixture = Path(__file__).parent / "fixtures" / "ledger_write_violation.py.txt"
    assert len(check_ledger_writes([fixture], allow={fixture})) == 0  # allowlisted -> clean
    assert len(check_ledger_writes([fixture], allow=set())) == 2


def test_no_ledger_writes_outside_service() -> None:
    violations = check_ledger_writes([CORE / "modules", VERSIONS], allow=LEDGER_ALLOWED)
    assert violations == [], (
        "coins.ledger_entries may only be written by modules/coins/service.py:\n"
        + "\n".join(violations)
    )
