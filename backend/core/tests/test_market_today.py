"""A-U1 W3 — GET /market/today/{pincode}: the flag-gated stub contract.

What A-U2 inherits: flag OFF is a 404 (the frontend renders NOTHING for
Today sections), flag ON serves the frozen TodayPayload shape, and the
stub is deterministic byte-for-byte (e2e asserts exact DOM from it).
"""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.flags import FeatureFlag, reset_flag_cache

from .d26_helpers import api  # noqa: F401 — the shared client fixture

pytestmark = pytest.mark.anyio

PINCODE = "641001"


async def _set_agri_today(session: AsyncSession, enabled: bool) -> None:
    flag = await session.get(FeatureFlag, "agri_today")
    assert flag is not None, "0037 seeds the agri_today flag"
    flag.enabled = enabled
    await session.flush()
    reset_flag_cache()


async def test_flag_off_is_404(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, session = api
    await _set_agri_today(session, False)
    r = await client.get(f"/market/today/{PINCODE}")
    assert r.status_code == 404
    assert r.json()["detail"] == "feature_disabled"


async def test_flag_on_serves_the_frozen_contract(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _set_agri_today(session, True)
    r = await client.get(f"/market/today/{PINCODE}")
    assert r.status_code == 200
    body = r.json()

    # Contract essentials the UI binds to (mirrored in packages/types).
    assert body["pincode"] == PINCODE
    assert body["stub"] is True
    assert len(body["weather"]["days"]) == 7
    assert body["weather"]["source"]
    assert body["weather"]["advisory"]["kind"] == "spray"
    assert body["severe_alert"]["district"] == "Coimbatore"
    assert body["mandi"]["source"] and body["mandi"]["as_of"]
    assert len(body["mandi"]["commodities"]) == 8
    for c in body["mandi"]["commodities"]:
        assert len(c["series_30d"]) >= 2  # sparkline needs a line
        assert {"en", "ta", "hi"} <= set(c["name"])  # TranslatedText everywhere
    assert len(body["calendar"]["months"]) == 8
    assert body["schemes"]["items"], "verified scheme entries"
    for item in body["schemes"]["items"]:
        assert item["verified_against"] and item["verified_on"]  # stamp from data
    assert any(d["chip"] == "72 HRS" for d in body["schemes"]["deadlines"])

    # Deterministic: two calls, identical bytes (e2e depends on this).
    again = await client.get(f"/market/today/{PINCODE}")
    assert again.content == r.content


async def test_non_reference_pincode_has_no_alert(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _set_agri_today(session, True)
    r = await client.get("/market/today/560001")
    assert r.status_code == 200
    body = r.json()
    assert body["severe_alert"] is None  # alert renders ONLY when active
    assert body["district"] is None


async def test_pincode_validation(api: tuple[httpx.AsyncClient, AsyncSession]) -> None:
    client, session = api
    await _set_agri_today(session, True)
    for bad in ("64100", "64100a", "6410011"):
        r = await client.get(f"/market/today/{bad}")
        assert r.status_code == 422, bad
