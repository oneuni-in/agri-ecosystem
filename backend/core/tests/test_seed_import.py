"""D27: seed bundle loading (pure) + DB import (Task 8 adds the DB class)."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from modules.directory.catalog_models import Product
from modules.directory.models import Business, BusinessCategory, Category
from modules.directory.seed_import import (
    SeedBranch,
    SeedBusiness,
    SeedContractError,
    SeedProduct,
    import_seed,
    load_bundle,
)

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


def _sample_bundle() -> list[SeedBusiness]:
    """Two businesses on tn_geo_sample pincodes: a vet (no products) and a
    dairy vendor (one milk product)."""
    return [
        SeedBusiness(
            ref="vet-1",
            name="Seed Vet Clinic",
            type="shop",
            category_slugs=("veterinarian",),
            primary_pincode="641001",
            description={"en": "Cattle vet", "ta": "கால்நடை மருத்துவர்", "hi": "पशु चिकित्सक"},
            branches=(
                SeedBranch(
                    address="5 Trichy Rd",
                    state="Tamil Nadu",
                    district="Coimbatore",
                    pincode="641001",
                    lat=None,
                    lng=None,
                ),
            ),
            coverage=("641001",),
            products=(),
        ),
        SeedBusiness(
            ref="dairy-1",
            name="Seed Fresh Dairy",
            type="vendor",
            category_slugs=("dairy",),
            primary_pincode="641001",
            description={"en": "Fresh milk"},
            branches=(
                SeedBranch(
                    address="6 Trichy Rd",
                    state="Tamil Nadu",
                    district="Coimbatore",
                    pincode="641001",
                    lat=Decimal("10.99"),
                    lng=Decimal("76.96"),
                ),
            ),
            coverage=("641001",),
            products=(
                SeedProduct(
                    vertical_slug="milk",
                    name="Fresh Cow Milk",
                    specs={"milk_type": "cow", "fat_percent": 4.2},
                    price_display="₹32/500ml",
                ),
            ),
        ),
    ]


class TestImportSeed:
    async def test_creates_ownerless_claimable_businesses(self, db_session, tn_geo_sample) -> None:
        report = await import_seed(db_session, _sample_bundle())
        assert report.created == 2 and report.skipped == 0
        vet = await db_session.scalar(select(Business).where(Business.name == "Seed Vet Clinic"))
        assert vet.owner_user_id is None  # claimable (D16)
        assert vet.status == "active"
        cats = (
            await db_session.scalars(
                select(Category.slug)
                .join(BusinessCategory, BusinessCategory.category_id == Category.id)
                .where(BusinessCategory.business_id == vet.id)
            )
        ).all()
        assert cats == ["veterinarian"]

    async def test_products_created_approved_with_pinned_schema(
        self, db_session, tn_geo_sample
    ) -> None:
        await import_seed(db_session, _sample_bundle())
        product = await db_session.scalar(
            select(Product)
            .join(Business, Business.id == Product.business_id)
            .where(Business.name == "Seed Fresh Dairy")
        )
        assert product.moderation_status == "approved"
        assert product.vertical_slug == "milk"
        assert product.schema_version is not None

    async def test_reimport_is_idempotent(self, db_session, tn_geo_sample) -> None:
        first = await import_seed(db_session, _sample_bundle())
        assert first.created == 2
        await db_session.flush()
        second = await import_seed(db_session, _sample_bundle())
        assert second.created == 0 and second.skipped == 2
        count = await db_session.scalar(
            select(func.count())
            .select_from(Business)
            .where(Business.name.in_(["Seed Vet Clinic", "Seed Fresh Dairy"]))
        )
        assert count == 2

    async def test_event_payloads_captured_for_created_only(
        self, db_session, tn_geo_sample
    ) -> None:
        first = await import_seed(db_session, _sample_bundle())
        types = [t for (t, _) in first.event_payloads]
        assert types.count("business.created") == 2
        assert types.count("product.created") == 1
        await db_session.flush()
        second = await import_seed(db_session, _sample_bundle())
        assert second.event_payloads == []

    async def test_unknown_category_slug_fails_loud(self, db_session, tn_geo_sample) -> None:
        bad = [
            replace(
                _sample_bundle()[0], ref="x", name="X Clinic", category_slugs=("no-such-category",)
            )
        ]
        with pytest.raises(SeedContractError, match="no-such-category"):
            await import_seed(db_session, bad)
