"""D30.A finding 5.1: fixture scripts must refuse a production database.

seed_e2e_milk.py grants the `staff` role - which gates every admin moderation
route - to a fixed phone number. Run against prod by accident, that is a staff
account on a number the operator does not control.
"""

import pytest

from settings import get_settings
from shared.dev_only import ProductionRefused, refuse_in_prod


def test_refuses_when_app_env_is_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    get_settings.cache_clear()
    try:
        with pytest.raises(ProductionRefused):
            refuse_in_prod("seed_e2e_milk.py")
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("env", ["dev", "test"])
def test_allows_dev_and_test(monkeypatch: pytest.MonkeyPatch, env: str) -> None:
    """CI runs seed_e2e_milk.py on every e2e job; a guard that fired here would
    take the whole D29 suite down."""
    monkeypatch.setenv("APP_ENV", env)
    get_settings.cache_clear()
    try:
        refuse_in_prod("seed_e2e_milk.py")  # must not raise
    finally:
        get_settings.cache_clear()


def test_the_guard_is_actually_wired_into_the_fixture_scripts() -> None:
    """The guard existing is worthless if nobody calls it. Assert the two
    fixture scripts import and invoke it - and that the two scripts which
    legitimately populate production do NOT."""
    from pathlib import Path

    scripts = Path(__file__).resolve().parent.parent / "scripts"
    for name in ("seed_e2e_milk.py", "make_business.py"):
        source = (scripts / name).read_text(encoding="utf-8")
        assert "refuse_in_prod(" in source, f"{name} does not call the prod guard"

    for name in ("load_geo.py", "import_vendor_seed.py"):
        source = (scripts / name).read_text(encoding="utf-8")
        assert "refuse_in_prod(" not in source, (
            f"{name} loads real production data (geo reference / the launch "
            f"vendor catalogue) and must stay runnable against prod"
        )
