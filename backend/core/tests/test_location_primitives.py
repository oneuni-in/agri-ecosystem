"""Location resolution primitives (D19 Task 6): nearest-pincode lookup +
optional GeoIP state provider. Both are advisory-only building blocks for
GET /identity/location (D19 Task 7) - neither is a source of truth on its
own."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import shared.geoip as geoip
from shared.geo.service import nearest_pincode
from shared.geoip import reset_geoip, state_for_ip


async def test_nearest_pincode_finds_coimbatore(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    result = await nearest_pincode(db_session, lat=10.9232, lon=76.9686)
    assert result is not None
    assert result.pincode == "641001"


async def test_nearest_pincode_finds_chennai(db_session: AsyncSession, tn_geo_sample: None) -> None:
    result = await nearest_pincode(db_session, lat=13.079, lon=80.287)
    assert result is not None
    assert result.pincode == "600001"


async def test_nearest_pincode_out_of_range_lat_returns_none(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    assert await nearest_pincode(db_session, lat=95, lon=76.9686) is None


async def test_nearest_pincode_out_of_range_lon_returns_none(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    assert await nearest_pincode(db_session, lat=10.9232, lon=-181) is None


async def test_nearest_pincode_empty_table_returns_none(db_session: AsyncSession) -> None:
    assert await nearest_pincode(db_session, lat=10.9232, lon=76.9686) is None


def test_state_for_ip_feature_off_by_default() -> None:
    reset_geoip()
    assert state_for_ip("103.21.244.1") is None


def test_state_for_ip_unparseable_ip_returns_none() -> None:
    reset_geoip()
    assert state_for_ip("not-an-ip") is None


def test_state_for_ip_success_with_fake_reader() -> None:
    reset_geoip()

    class FakeReader:
        def get(self, ip: str) -> dict[str, object]:
            return {
                "country": {"iso_code": "IN"},
                "subdivisions": [{"names": {"en": "Tamil Nadu"}}],
            }

    geoip._reader = FakeReader()
    try:
        assert state_for_ip("103.21.244.1") == "Tamil Nadu"
    finally:
        reset_geoip()


def test_state_for_ip_non_india_returns_none() -> None:
    reset_geoip()

    class FakeReader:
        def get(self, ip: str) -> dict[str, object]:
            return {
                "country": {"iso_code": "US"},
                "subdivisions": [{"names": {"en": "California"}}],
            }

    geoip._reader = FakeReader()
    try:
        assert state_for_ip("8.8.8.8") is None
    finally:
        reset_geoip()


def test_state_for_ip_reader_raising_returns_none() -> None:
    reset_geoip()

    class RaisingReader:
        def get(self, ip: str) -> dict[str, object]:
            raise RuntimeError("boom")

    geoip._reader = RaisingReader()
    try:
        assert state_for_ip("103.21.244.1") is None
    finally:
        reset_geoip()


@pytest.mark.parametrize(
    "record",
    [
        {"country": None},
        {"country": {"iso_code": "IN"}, "subdivisions": {}},
        {"country": {"iso_code": "IN"}, "subdivisions": ["notadict"]},
        {"country": {"iso_code": "IN"}, "subdivisions": [{"names": "notadict"}]},
    ],
    ids=[
        "null-country",
        "subdivisions-not-a-list",
        "subdivision-entry-not-a-dict",
        "names-not-a-dict",
    ],
)
def test_state_for_ip_malformed_record_shapes_return_none(record: object) -> None:
    """Advisory-only, called from a public endpoint (Task 7): any
    plausible-but-malformed mmdb record shape must degrade to None, never
    raise (a raise here would become a 500 for the caller)."""
    reset_geoip()

    class FakeReader:
        def get(self, ip: str) -> object:
            return record

    geoip._reader = FakeReader()
    try:
        assert state_for_ip("103.21.244.1") is None
    finally:
        reset_geoip()
