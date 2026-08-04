"""M4 population snapshot integrity - pure file checks, no DB."""

import csv
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "geo"


def _population_rows() -> dict[str, int]:
    with (DATA_DIR / "pincode_population.csv").open(encoding="utf-8") as fh:
        return {row["pincode"]: int(row["population"]) for row in csv.DictReader(fh)}


def test_every_tn_pincode_has_a_population_row() -> None:
    with (DATA_DIR / "pincodes.csv").open(encoding="utf-8") as fh:
        tn = {row["pincode"] for row in csv.DictReader(fh)}
    missing = tn - _population_rows().keys()
    assert not missing, f"TN pincodes without population: {sorted(missing)[:10]}"


def test_populations_are_sane() -> None:
    pops = _population_rows()
    assert len(pops) > 15_000  # pan-India universe loaded, not just TN
    assert all(p >= 0 for p in pops.values())
    assert pops["641001"] > 0


def test_grades_are_valid() -> None:
    with (DATA_DIR / "pincode_population.csv").open(encoding="utf-8") as fh:
        grades = {row["grade"] for row in csv.DictReader(fh)}
    assert grades <= {"town", "village", "district_apportioned"}
