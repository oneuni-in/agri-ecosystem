"""D19 Task 12: pure-function tests for the Coimbatore vendor-seed
normalizer (backend/core/scripts/normalize_vendor_seed.py) - no DB.

Covers normalize_row, validate_pincode (valid / not-in-geo / wrong-district),
looks_like_pii (phone/email shapes), dedupe, and confirms the shipped
starter CSVs (data/seeds/coimbatore/*.csv - a ~15-row starter sample,
NOT real vendor data, see README.md) actually parse and validate against
the D27 import-CSV contract end to end."""

import csv
import json
from pathlib import Path

import pytest

from modules.directory.specs import parse_fields, validate_specs
from scripts.normalize_vendor_seed import (
    ADJACENT_LGD_CODES,
    COIMBATORE_LGD,
    MILK_SPEC_FIELDS,
    GeoPincode,
    dedupe,
    load_geo,
    looks_like_pii,
    normalize_row,
    validate_pincode,
)

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seeds" / "coimbatore"
GEO_PATH = Path(__file__).resolve().parents[1] / "data" / "geo" / "pincodes.csv"

GEO = {
    "641001": GeoPincode(district_lgd_code="569", lat="10.9232", lng="76.9686"),
    "641045": GeoPincode(district_lgd_code="569", lat="10.9111", lng="77.0415"),
    "641604": GeoPincode(
        district_lgd_code="634", lat="10.8962", lng="77.0504"
    ),  # Tiruppur - adjacent
    "600001": GeoPincode(
        district_lgd_code="568", lat="13.0914", lng="80.2828"
    ),  # Chennai - out of area
}


def _row(**overrides: str) -> dict[str, str]:
    base = {
        "name": "  Sri  Balaji   Dairy  ",
        "type": "vendor",
        "category_slugs": "dairy",
        "primary_pincode": "641001",
        "description_en": "Fresh cow milk daily doorstep delivery",
        "description_ta": "",
        "description_hi": "",
        "address": "Shop 4, RS Puram",
        "state": "Tamil Nadu",
        "district": "Coimbatore",
        "pincode": "641001",
        "lat": "",
        "lng": "",
        "coverage_pincodes": "641001;641045",
        "vertical_slug": "milk",
        "product_name": "Fresh Cow Milk",
        "milk_type": "cow",
        "fat_percent": "4.2",
        "pack_size": "500ml",
        "price_display": "₹32/500ml",
    }
    base.update(overrides)
    return base


class TestLooksLikePii:
    def test_blank_is_clean(self) -> None:
        assert looks_like_pii("") is False

    def test_plain_text_is_clean(self) -> None:
        assert looks_like_pii("Fresh cow milk daily doorstep delivery") is False

    def test_pincode_alone_is_not_flagged(self) -> None:
        assert looks_like_pii("641001") is False

    @pytest.mark.parametrize(
        "value",
        [
            "call 9876543210 for orders",
            "+91 98765 43210",
            "987-654-3210 available",
            "reach us on 09876543210",
            "call 987.654.3210 for orders",  # dot-separated
            "call 987/654/3210 for orders",  # slash-separated
            "call +91-987.654/3210 for orders",  # mixed separators
            "whatsapp only (987) 654-3210",  # parens + hyphen mixed
        ],
    )
    def test_phone_shapes_are_flagged(self, value: str) -> None:
        assert looks_like_pii(value) is True

    def test_price_with_slash_is_not_flagged(self) -> None:
        # A slash is legitimate in "₹32/500ml" price_display strings -
        # only flag when the digit run either side actually clears 10.
        assert looks_like_pii("₹32/500ml") is False
        assert looks_like_pii("₹58/L (bulk)") is False

    @pytest.mark.parametrize(
        "value",
        [
            "reach us at vendor@example.com",
            "sales.desk+coimbatore@shop.co.in",
        ],
    )
    def test_email_shapes_are_flagged(self, value: str) -> None:
        assert looks_like_pii(value) is True


class TestValidatePincode:
    def test_valid_home_district(self) -> None:
        assert validate_pincode("641001", GEO) is None

    def test_valid_adjacent_district(self) -> None:
        assert validate_pincode("641604", GEO) is None

    def test_not_in_geo(self) -> None:
        assert validate_pincode("999999", GEO) == "pincode_not_found"

    def test_wrong_district(self) -> None:
        assert validate_pincode("600001", GEO) == "pincode_outside_service_area"

    def test_adjacent_allowlist_is_explicit_and_coimbatore_is_569(self) -> None:
        assert ADJACENT_LGD_CODES
        assert COIMBATORE_LGD == "569"
        assert COIMBATORE_LGD not in ADJACENT_LGD_CODES


class TestNormalizeRow:
    def test_accepts_clean_row(self) -> None:
        record, reason = normalize_row(_row(), GEO)
        assert reason is None
        assert record is not None
        assert record.business["name"] == "Sri Balaji Dairy"
        assert record.business["type"] == "vendor"
        assert record.business["primary_pincode"] == "641001"
        assert record.branch["business_ref"] == record.business["ref"]
        assert {c["pincode"] for c in record.coverage} == {"641001", "641045"}
        assert len(record.products) == 1
        specs = json.loads(record.products[0]["specs_json"])
        assert specs["milk_type"] == "cow"

    def test_type_casing_normalized(self) -> None:
        record, reason = normalize_row(_row(type="VENDOR"), GEO)
        assert reason is None
        assert record is not None
        assert record.business["type"] == "vendor"

    def test_rejects_unknown_type(self) -> None:
        _, reason = normalize_row(_row(type="wholesaler"), GEO)
        assert reason is not None and reason.startswith("invalid_type")

    def test_rejects_missing_category(self) -> None:
        _, reason = normalize_row(_row(category_slugs=""), GEO)
        assert reason == "missing_category"

    def test_rejects_unknown_category(self) -> None:
        _, reason = normalize_row(_row(category_slugs="butchery"), GEO)
        assert reason is not None and reason.startswith("invalid_category")

    def test_rejects_report_all_unknown_categories_not_just_first(self) -> None:
        _, reason = normalize_row(_row(category_slugs="butchery;fishery;dairy"), GEO)
        assert reason == "invalid_category:butchery,fishery"

    def test_rejects_pincode_not_in_geo(self) -> None:
        _, reason = normalize_row(_row(primary_pincode="999999", pincode="999999"), GEO)
        assert reason is not None and reason.startswith("pincode_not_found")

    def test_rejects_out_of_area_pincode(self) -> None:
        _, reason = normalize_row(_row(primary_pincode="600001", pincode="600001"), GEO)
        assert reason is not None and reason.startswith("pincode_outside_service_area")

    def test_rejects_phone_in_address(self) -> None:
        _, reason = normalize_row(_row(address="Shop 4, RS Puram, call 9876543210"), GEO)
        assert reason == "pii_detected:address"

    def test_rejects_email_in_description(self) -> None:
        _, reason = normalize_row(_row(description_en="mail us at vendor@example.com"), GEO)
        assert reason == "pii_detected:description_en"

    def test_rejects_phone_in_description_hi(self) -> None:
        _, reason = normalize_row(_row(description_hi="ऑर्डर के लिए 9876543210 पर कॉल करें"), GEO)
        assert reason == "pii_detected:description_hi"

    def test_rejects_phone_in_name(self) -> None:
        _, reason = normalize_row(_row(name="Sri Balaji Dairy 9876543210"), GEO)
        assert reason == "pii_detected:name"

    def test_rejects_phone_in_price_display(self) -> None:
        _, reason = normalize_row(_row(price_display="₹32/500ml, call 9876543210 for bulk"), GEO)
        assert reason == "pii_detected:price_display"

    def test_rejects_phone_in_state(self) -> None:
        _, reason = normalize_row(_row(state="Tamil Nadu (call 9876543210)"), GEO)
        assert reason == "pii_detected:state"

    def test_rejects_email_in_district(self) -> None:
        _, reason = normalize_row(_row(district="Coimbatore vendor@example.com"), GEO)
        assert reason == "pii_detected:district"

    def test_rejects_dot_separated_phone_in_address(self) -> None:
        _, reason = normalize_row(_row(address="Shop 4, RS Puram, 987.654.3210"), GEO)
        assert reason == "pii_detected:address"

    def test_rejects_slash_separated_phone_in_address(self) -> None:
        _, reason = normalize_row(_row(address="Shop 4, RS Puram, 987/654/3210"), GEO)
        assert reason == "pii_detected:address"

    def test_rejects_invalid_milk_enum_value(self) -> None:
        _, reason = normalize_row(_row(milk_type="camel"), GEO)
        assert reason is not None and reason.startswith("invalid_specs")

    def test_rejects_out_of_range_fat_percent(self) -> None:
        _, reason = normalize_row(_row(fat_percent="99"), GEO)
        assert reason is not None and reason.startswith("invalid_specs")

    def test_no_product_when_vertical_blank(self) -> None:
        record, reason = normalize_row(_row(vertical_slug=""), GEO)
        assert reason is None
        assert record is not None
        assert record.products == []

    def test_optional_specs_may_be_blank(self) -> None:
        record, reason = normalize_row(_row(fat_percent="", pack_size=""), GEO)
        assert reason is None
        assert record is not None
        specs = json.loads(record.products[0]["specs_json"])
        assert specs == {"milk_type": "cow"}

    def test_missing_required_milk_type_rejected(self) -> None:
        _, reason = normalize_row(_row(milk_type=""), GEO)
        assert reason is not None and reason.startswith("invalid_specs")


class TestDedupe:
    def test_drops_second_occurrence_same_name_and_pincode(self) -> None:
        rec1, _ = normalize_row(_row(), GEO)
        rec2, _ = normalize_row(_row(address="Shop 9, Different Street"), GEO)
        assert rec1 is not None and rec2 is not None
        kept, dupes = dedupe([({"row": "1"}, rec1), ({"row": "2"}, rec2)])
        assert len(kept) == 1
        assert len(dupes) == 1
        assert dupes[0][1] == "duplicate"

    def test_keeps_same_name_different_pincode(self) -> None:
        rec1, _ = normalize_row(_row(), GEO)
        rec2, _ = normalize_row(
            _row(primary_pincode="641045", pincode="641045", coverage_pincodes="641045"), GEO
        )
        assert rec1 is not None and rec2 is not None
        kept, dupes = dedupe([({}, rec1), ({}, rec2)])
        assert len(kept) == 2
        assert dupes == []


class TestStarterSeed:
    """The four data/seeds/coimbatore/*.csv files are a ~15-row STARTER
    SAMPLE, not real vendor data (see README.md) - but they must be
    well-formed against the same contract the normalizer emits."""

    def _rows(self, name: str) -> list[dict[str, str]]:
        with (SEED_DIR / name).open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def test_starter_files_exist_and_parse(self) -> None:
        for name in ("businesses.csv", "branches.csv", "coverage.csv", "products.csv"):
            rows = self._rows(name)
            assert rows, f"{name} is empty"

    def test_row_count_is_a_small_starter_sample(self) -> None:
        businesses = self._rows("businesses.csv")
        assert 10 <= len(businesses) <= 20

    def test_refs_are_unique_and_join_across_files(self) -> None:
        businesses = self._rows("businesses.csv")
        refs = {b["ref"] for b in businesses}
        assert len(refs) == len(businesses)
        for name, key in (
            ("branches.csv", "business_ref"),
            ("coverage.csv", "business_ref"),
            ("products.csv", "business_ref"),
        ):
            joined = {row[key] for row in self._rows(name)}
            assert joined, f"{name} has no rows"
            assert joined <= refs, f"{name} references a ref not in businesses.csv"

    def test_pincodes_are_real_coimbatore_geo(self) -> None:
        geo = load_geo(GEO_PATH)
        for row in self._rows("businesses.csv"):
            assert validate_pincode(row["primary_pincode"], geo) is None
        for row in self._rows("branches.csv"):
            assert validate_pincode(row["pincode"], geo) is None
        for row in self._rows("coverage.csv"):
            assert validate_pincode(row["pincode"], geo) is None

    def test_category_is_dairy(self) -> None:
        for row in self._rows("businesses.csv"):
            assert "dairy" in row["category_slugs"].split(";")

    def test_product_specs_validate_against_milk_schema(self) -> None:
        fields = parse_fields(MILK_SPEC_FIELDS)
        products = self._rows("products.csv")
        assert products
        for row in products:
            specs = json.loads(row["specs_json"])
            validate_specs(specs, fields)  # raises SpecValidationError on failure

    def test_no_pii_columns_in_contract(self) -> None:
        for name in ("businesses.csv", "branches.csv", "coverage.csv", "products.csv"):
            with (SEED_DIR / name).open(newline="", encoding="utf-8") as fh:
                header = next(csv.reader(fh))
            for banned in ("phone", "whatsapp", "email"):
                assert banned not in header, f"{name} has a banned {banned} column"

    def test_no_pii_looking_values_in_free_text_fields(self) -> None:
        for row in self._rows("businesses.csv"):
            assert not looks_like_pii(row["name"])
            assert not looks_like_pii(row["description_en"])
            assert not looks_like_pii(row["description_ta"])
            assert not looks_like_pii(row["description_hi"])
        for row in self._rows("branches.csv"):
            assert not looks_like_pii(row["address"])
            assert not looks_like_pii(row["state"])
            assert not looks_like_pii(row["district"])
        for row in self._rows("products.csv"):
            assert not looks_like_pii(row["name"])
            assert not looks_like_pii(row["price_display"])

    def test_rejects_csv_is_gitignored(self) -> None:
        # rejects.csv holds raw, unredacted PII (see script docstring) -
        # this directory must never be able to commit it silently.
        gitignore = (SEED_DIR / ".gitignore").read_text(encoding="utf-8")
        assert "rejects.csv" in gitignore


def test_businesses_csv_has_hindi_descriptions() -> None:
    with (SEED_DIR / "businesses.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows, "starter sample must not be empty"
    for row in rows:
        assert "description_hi" in row
        assert row["description_hi"].strip(), row["ref"]


def test_dairy_service_categories_are_valid_seed_slugs() -> None:
    from scripts.normalize_vendor_seed import CATEGORY_SLUGS

    assert {"veterinarian", "feed-supplier", "dairy-farm", "cooperative"} <= CATEGORY_SLUGS
