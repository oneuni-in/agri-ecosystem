"""D27: seed bundle loading (pure) + DB import (Task 8 adds the DB class)."""

from decimal import Decimal
from pathlib import Path

import pytest

from modules.directory.seed_import import SeedContractError, load_bundle

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seeds" / "coimbatore"


def _write_bundle(tmp_path: Path, **overrides: str) -> Path:
    files = {
        "businesses.csv": (
            "ref,name,type,category_slugs,primary_pincode,description_en,description_ta,description_hi\n"
            "b1,Test Dairy,vendor,dairy,641001,Fresh milk,புதிய பால்,ताज़ा दूध\n"
        ),
        "branches.csv": (
            "business_ref,address,state,district,pincode,lat,lng\n"
            "b1,1 Main Rd,Tamil Nadu,Coimbatore,641001,10.99,76.96\n"
        ),
        "coverage.csv": "business_ref,pincode\nb1,641001\n",
        "products.csv": (
            "business_ref,vertical_slug,name,specs_json,price_display\n"
            'b1,milk,Fresh Cow Milk,"{""milk_type"": ""cow""}",₹32/500ml\n'
        ),
    }
    files.update(overrides)
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return tmp_path


class TestLoadBundle:
    def test_loads_starter_sample(self) -> None:
        bundle = load_bundle(SEED_DIR)
        assert len(bundle) >= 15
        first = bundle[0]
        assert first.branches and first.coverage
        assert set(first.description) >= {"en"}

    def test_happy_path_shapes(self, tmp_path: Path) -> None:
        [business] = load_bundle(_write_bundle(tmp_path))
        assert business.ref == "b1"
        assert business.branches[0].lat == Decimal("10.99")
        assert business.products[0].specs == {"milk_type": "cow"}
        assert business.description == {"en": "Fresh milk", "ta": "புதிய பால்", "hi": "ताज़ा दूध"}

    def test_orphan_branch_ref_rejected(self, tmp_path: Path) -> None:
        seed_dir = _write_bundle(
            tmp_path,
            **{
                "branches.csv": (
                    "business_ref,address,state,district,pincode,lat,lng\n"
                    "GHOST,1 Main Rd,Tamil Nadu,Coimbatore,641001,,\n"
                )
            },
        )
        with pytest.raises(SeedContractError, match="GHOST"):
            load_bundle(seed_dir)

    def test_bad_pincode_rejected(self, tmp_path: Path) -> None:
        seed_dir = _write_bundle(
            tmp_path,
            **{"coverage.csv": "business_ref,pincode\nb1,64100\n"},
        )
        with pytest.raises(SeedContractError, match="64100"):
            load_bundle(seed_dir)

    def test_bad_type_rejected(self, tmp_path: Path) -> None:
        seed_dir = _write_bundle(
            tmp_path,
            **{
                "businesses.csv": (
                    "ref,name,type,category_slugs,primary_pincode,description_en,description_ta,description_hi\n"
                    "b1,Test Dairy,supermarket,dairy,641001,Fresh milk,,\n"
                )
            },
        )
        with pytest.raises(SeedContractError, match="supermarket"):
            load_bundle(seed_dir)

    def test_business_without_branch_rejected(self, tmp_path: Path) -> None:
        seed_dir = _write_bundle(
            tmp_path, **{"branches.csv": "business_ref,address,state,district,pincode,lat,lng\n"}
        )
        with pytest.raises(SeedContractError, match="b1"):
            load_bundle(seed_dir)

    def test_bad_specs_json_rejected(self, tmp_path: Path) -> None:
        seed_dir = _write_bundle(
            tmp_path,
            **{
                "products.csv": (
                    "business_ref,vertical_slug,name,specs_json,price_display\n"
                    "b1,milk,Broken,not-json,\n"
                )
            },
        )
        with pytest.raises(SeedContractError, match="not-json|specs"):
            load_bundle(seed_dir)

    def test_blank_specs_json_rejected(self, tmp_path: Path) -> None:
        seed_dir = _write_bundle(
            tmp_path,
            **{
                "products.csv": (
                    "business_ref,vertical_slug,name,specs_json,price_display\n"
                    "b1,milk,Blank Specs,,\n"
                )
            },
        )
        with pytest.raises(SeedContractError, match="specs"):
            load_bundle(seed_dir)
