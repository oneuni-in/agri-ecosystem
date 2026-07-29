"""Refuse to run against a production database (D30.A finding 5.1).

Some scripts here exist to fabricate test state. Pointed at prod - a stale
DATABASE_URL in a shell, a copy-pasted command, an ops box with prod env
loaded - they write demo businesses and, worse, seeded identities into real
data. seed_e2e_milk.py grants the `staff` role, which gates every admin
moderation route, to a fixed phone number; if that number is allocatable and
someone else holds it, they can request an OTP and sign in as staff.

Scripts that legitimately populate production (load_geo.py's reference data,
import_vendor_seed.py's real vendor catalogue) deliberately do NOT call this.
"""

from settings import get_settings


class ProductionRefused(RuntimeError):
    """Raised instead of writing fixtures into a production database."""


def refuse_in_prod(script: str) -> None:
    """Abort when app_env is prod. Call before the first write."""
    if get_settings().app_env == "prod":
        raise ProductionRefused(
            f"{script} fabricates test data and must never run against production. "
            "APP_ENV=prod - refusing. If you meant a different database, check "
            "DATABASE_URL and APP_ENV in this shell."
        )
