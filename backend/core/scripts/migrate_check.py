"""CI gate: prove every migration upgrades AND downgrades cleanly.

Runs upgrade -> head, downgrade -> base, upgrade -> head against the database
in ALEMBIC_DATABASE_URL (falling back to settings.database_admin_url - alembic
needs DDL rights that the runtime app_rt role does not have, D12). Run from
backend/core:

    python scripts/migrate_check.py
"""

import subprocess
import sys


def _alembic(*args: str) -> None:
    command = [sys.executable, "-m", "alembic", *args]
    print(f"$ {' '.join(command[2:])}", flush=True)  # noqa: T201 - CI progress output
    subprocess.run(command, check=True)


def main() -> int:
    for step in (("upgrade", "head"), ("downgrade", "base"), ("upgrade", "head")):
        _alembic(*step)
    print("migrate_check: all migrations upgrade and downgrade cleanly", flush=True)  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
