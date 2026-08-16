"""Pure, DB-free validation of the education seed bundle (spec §8).

Imported by scripts/validate_education_seed.py and, at integration time, by
modules/education/seed_import.py. Deliberately has NO database dependency:
geo reference data is read from the committed CSVs so validation runs in CI
and on a laptop with no Postgres.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

FILES = (
    "institutions.csv",
    "programmes.csv",
    "institution_programmes.csv",
    "student_resources.csv",
    "guides.csv",
)

RESERVED_SLUGS = frozenset({"state", "abroad"})

INSTITUTION_KINDS = frozenset(
    {
        "central_agri_university",
        "state_agri_university",
        "deemed_university",
        "icar_institute",
        "private_university",
        "affiliated_college",
        "constituent_college",
        "foreign_university",
    }
)
TRUST_VALUES = frozenset({"verified", "listed"})
INSTITUTION_STATUSES = frozenset({"active", "closed", "merged"})
PROGRAMME_LEVELS = frozenset({"diploma", "ug", "pg", "phd"})
DISCIPLINES = frozenset(
    {
        "agriculture",
        "horticulture",
        "forestry",
        "fisheries",
        "dairy_tech",
        "agri_engineering",
        "agri_business",
        "veterinary",
    }
)
RESOURCE_KINDS = frozenset({"scholarship", "exam"})
RESOURCE_CATEGORIES = frozenset({"entrance", "recruitment", "language_test"})
RESOURCE_SCOPES = frozenset({"india", "international"})
GUIDE_KINDS = frozenset({"counselling", "foreign_study", "general"})


class SeedContractError(Exception):
    """Raised with EVERY violation found, so one run fixes many rows."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__("\n".join(violations))


@dataclass
class Bundle:
    institutions: list[dict[str, str]] = field(default_factory=list)
    programmes: list[dict[str, str]] = field(default_factory=list)
    institution_programmes: list[dict[str, str]] = field(default_factory=list)
    student_resources: list[dict[str, str]] = field(default_factory=list)
    guides: list[dict[str, str]] = field(default_factory=list)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def load_bundle(seed_dir: Path) -> Bundle:
    violations = [f"missing {name}" for name in FILES if not (seed_dir / name).is_file()]
    if violations:
        raise SeedContractError(violations)
    return Bundle(
        institutions=_read_csv(seed_dir / "institutions.csv"),
        programmes=_read_csv(seed_dir / "programmes.csv"),
        institution_programmes=_read_csv(seed_dir / "institution_programmes.csv"),
        student_resources=_read_csv(seed_dir / "student_resources.csv"),
        guides=_read_csv(seed_dir / "guides.csv"),
    )
