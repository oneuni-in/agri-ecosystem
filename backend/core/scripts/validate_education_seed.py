"""Validate the committed education seed bundle against the spec §8 contract.

    cd backend/core
    python -m scripts.validate_education_seed             # the committed bundle
    python -m scripts.validate_education_seed --seed-dir /tmp/batch

Exit 0 = clean. Exit 1 = violations printed, one per line. No database is
required: geo reference data is read from data/geo/*.csv.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.education_seed_contract import (  # noqa: E402
    SeedContractError,
    load_bundle,
    load_geo_reference,
    validate,
)

_ROOT = Path(__file__).resolve().parents[1]


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-dir", type=Path, default=_ROOT / "data" / "seeds" / "education")
    parser.add_argument("--geo-dir", type=Path, default=_ROOT / "data" / "geo")
    args = parser.parse_args(argv)

    try:
        bundle = load_bundle(args.seed_dir)
        validate(
            bundle,
            load_geo_reference(args.geo_dir),
            today=datetime.now(UTC).date(),
        )
    except SeedContractError as exc:
        print(f"CONTRACT VIOLATIONS ({len(exc.violations)}) - nothing importable:")  # noqa: T201
        for violation in exc.violations:
            print(f"  {violation}")  # noqa: T201
        return 1

    print(  # noqa: T201
        f"bundle OK: {len(bundle.institutions)} institutions, "
        f"{len(bundle.programmes)} programmes, "
        f"{len(bundle.institution_programmes)} institution-programmes, "
        f"{len(bundle.student_resources)} resources, {len(bundle.guides)} guides"
    )
    return 0


def main() -> int:
    return _main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
