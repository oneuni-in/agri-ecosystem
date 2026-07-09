"""Repo-wide lint contracts that ruff cannot express: the THREAT/NOTES block
is mandatory in every migration."""

from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
VERSIONS = CORE / "alembic" / "versions"


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
