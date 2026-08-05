"""M5 Task 6: advertiser self-serve campaign API. NN4 is the point of this
file - `_owned_campaign` must 404 (never 403) on every read/write that isn't
the caller's own business, so ownership can never be used as an oracle."""

import uuid
from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads.models import Campaign
from modules.directory import service as directory_service
from shared.flags import FeatureFlag, reset_flag_cache
from tests.d26_helpers import _as, api  # noqa: F401 (pytest fixture injection)

pytestmark = pytest.mark.asyncio

OWNER = uuid.uuid4()
STRANGER = uuid.uuid4()
PINCODE = "641001"


async def _enable_ads(session: AsyncSession) -> None:
    flag = await session.get(FeatureFlag, "ads_enabled")
    assert flag is not None
    flag.enabled = True
    await session.flush()
    reset_flag_cache()


async def _business(session: AsyncSession, owner: uuid.UUID = OWNER) -> uuid.UUID:
    business = await directory_service.create_business(
        session,
        owner_user_id=owner,
        name=f"Advertiser {uuid.uuid4().hex[:8]}",
        type_="shop",
        primary_pincode=PINCODE,
    )
    return business.id


def _quote_body(**overrides: Any) -> dict[str, Any]:
    today = date.today()
    body: dict[str, Any] = {
        "slot_keys": ["milk_home_hero"],
        "geo_target": {},
        "categories": [],
        "flight_start": (today + timedelta(days=1)).isoformat(),
        "flight_end": (today + timedelta(days=15)).isoformat(),
        "serves_total": 5000,
    }
    body.update(overrides)
    return body


async def _create_draft(
    client: httpx.AsyncClient,
    session: AsyncSession,
    *,
    owner: uuid.UUID = OWNER,
    name: str = "Draft campaign",
    **quote_overrides: Any,
) -> dict[str, Any]:
    business_id = await _business(session, owner=owner)
    body = {**_quote_body(**quote_overrides), "business_id": str(business_id), "name": name}
    resp = await client.post("/ads/my/campaigns", json=body, headers=_as(owner))
    assert resp.status_code == 201, resp.text
    result: dict[str, Any] = resp.json()
    return result


async def test_quote_then_create_draft_happy_path(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    business_id = await _business(session)

    body = _quote_body(geo_target={"tiers": [2, 3]}, categories=["ghee"])
    quote_resp = await client.post("/ads/my/quote", json=body, headers=_as(OWNER))
    assert quote_resp.status_code == 200, quote_resp.text
    quote = quote_resp.json()
    assert quote["pricing_model"] == "cpm"
    assert quote["tier"] == 2  # min([2, 3])
    assert quote["total_paise"] == quote["subtotal_paise"] + quote["gst_paise"]

    create_body = {
        **body,
        "business_id": str(business_id),
        "name": "Kharif push",
        "daily_serve_cap": 500,
    }
    create_resp = await client.post("/ads/my/campaigns", json=create_body, headers=_as(OWNER))
    assert create_resp.status_code == 201, create_resp.text
    campaign = create_resp.json()

    assert campaign["status"] == "draft"
    assert campaign["display_status"] == "draft"
    assert campaign["advertiser_business_id"] == str(business_id)
    assert campaign["price_paise"] == quote["total_paise"]
    assert campaign["price_subtotal_paise"] == quote["subtotal_paise"]
    assert campaign["price_gst_paise"] == quote["gst_paise"]
    assert campaign["rate_card_version"] == quote["rate_card_version"]
    assert campaign["pricing_model"] == quote["pricing_model"]
    assert campaign["budget_serves_total"] == quote["serves_total"]
    assert campaign["daily_serve_cap"] == 500
    assert campaign["creatives"] == []

    assert len(campaign["placements"]) == 1
    placement = campaign["placements"][0]
    assert placement["slot_key"] == "milk_home_hero"
    assert placement["status"] == "active"
    assert placement["geo_target"]["tiers"] == [2, 3]
    assert placement["geo_target"]["categories"] == ["ghee"]

    # GET returns the same snapshot
    get_resp = await client.get(f"/ads/my/campaigns/{campaign['id']}", headers=_as(OWNER))
    assert get_resp.status_code == 200
    assert get_resp.json() == campaign


async def test_create_rejects_unowned_business_404(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    foreign_business_id = await _business(session, owner=STRANGER)

    body = {**_quote_body(), "business_id": str(foreign_business_id), "name": "Not mine"}
    resp = await client.post("/ads/my/campaigns", json=body, headers=_as(OWNER))
    assert resp.status_code == 404

    unknown_body = {**_quote_body(), "business_id": str(uuid.uuid4()), "name": "Ghost business"}
    unknown_resp = await client.post("/ads/my/campaigns", json=unknown_body, headers=_as(OWNER))
    assert unknown_resp.status_code == 404


async def test_get_foreign_campaign_404(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session, owner=OWNER)

    foreign = await client.get(f"/ads/my/campaigns/{campaign['id']}", headers=_as(STRANGER))
    assert foreign.status_code == 404

    own = await client.get(f"/ads/my/campaigns/{campaign['id']}", headers=_as(OWNER))
    assert own.status_code == 200

    missing = await client.get(f"/ads/my/campaigns/{uuid.uuid4()}", headers=_as(OWNER))
    assert missing.status_code == 404


async def test_patch_foreign_campaign_404(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session, owner=OWNER)

    foreign = await client.patch(
        f"/ads/my/campaigns/{campaign['id']}", json={"name": "Hijacked"}, headers=_as(STRANGER)
    )
    assert foreign.status_code == 404

    check = await client.get(f"/ads/my/campaigns/{campaign['id']}", headers=_as(OWNER))
    assert check.json()["name"] == "Draft campaign"  # untouched by the foreign attempt


async def test_list_only_own_campaigns(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    mine_1 = await _create_draft(client, session, owner=OWNER, name="Mine 1")
    mine_2 = await _create_draft(client, session, owner=OWNER, name="Mine 2")
    theirs = await _create_draft(client, session, owner=STRANGER, name="Theirs")

    resp = await client.get("/ads/my/campaigns", headers=_as(OWNER))
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()["items"]}
    assert ids == {mine_1["id"], mine_2["id"]}
    assert theirs["id"] not in ids

    # a caller who owns no businesses gets an empty page, not an error
    nobody = uuid.uuid4()
    empty = await client.get("/ads/my/campaigns", headers=_as(nobody))
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "next_cursor": None}

    # business_id scoping to one's own business narrows the page
    scoped = await client.get(
        f"/ads/my/campaigns?business_id={mine_1['advertiser_business_id']}", headers=_as(OWNER)
    )
    assert scoped.status_code == 200
    assert {item["id"] for item in scoped.json()["items"]} == {mine_1["id"]}

    # business_id scoping to a business you don't own is 404, not an oracle
    foreign_scope = await client.get(
        f"/ads/my/campaigns?business_id={theirs['advertiser_business_id']}", headers=_as(OWNER)
    )
    assert foreign_scope.status_code == 404


async def test_flag_off_404s_everything(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, _ = api
    business_id = uuid.uuid4()
    campaign_id = uuid.uuid4()
    cases: list[tuple[str, str, dict[str, Any]]] = [
        ("POST", "/ads/my/quote", {"json": _quote_body()}),
        (
            "POST",
            "/ads/my/campaigns",
            {"json": {**_quote_body(), "business_id": str(business_id), "name": "x"}},
        ),
        ("GET", "/ads/my/campaigns", {}),
        ("GET", f"/ads/my/campaigns/{campaign_id}", {}),
        ("PATCH", f"/ads/my/campaigns/{campaign_id}", {"json": {"name": "y"}}),
    ]
    for method, path, kwargs in cases:
        resp = await client.request(method, path, headers=_as(OWNER), **kwargs)
        assert resp.status_code == 404, (path, resp.text)


async def test_patch_reprices_on_targeting_change(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(
        client, session, geo_target={"tiers": [3]}, categories=[], serves_total=5000
    )
    original_price = campaign["price_paise"]

    # targeting change: adding the ghee multiplier must move the price
    add_category = await client.patch(
        f"/ads/my/campaigns/{campaign['id']}",
        json={"categories": ["ghee"]},
        headers=_as(OWNER),
    )
    assert add_category.status_code == 200, add_category.text
    repriced = add_category.json()
    assert repriced["price_paise"] != original_price
    assert repriced["placements"][0]["geo_target"]["categories"] == ["ghee"]
    # untouched targeting (tiers) survives the partial update
    assert repriced["placements"][0]["geo_target"]["tiers"] == [3]
    assert repriced["rate_card_version"] == campaign["rate_card_version"]

    # budget change: a bigger serves_total must move the price again
    bigger_budget = await client.patch(
        f"/ads/my/campaigns/{campaign['id']}",
        json={"serves_total": 20000},
        headers=_as(OWNER),
    )
    assert bigger_budget.status_code == 200, bigger_budget.text
    rebudgeted = bigger_budget.json()
    assert rebudgeted["budget_serves_total"] == 20000
    assert rebudgeted["price_paise"] > repriced["price_paise"]
    # categories from the previous patch must survive this one too
    assert rebudgeted["placements"][0]["geo_target"]["categories"] == ["ghee"]

    # a non-repricing field (name) leaves the price untouched
    renamed = await client.patch(
        f"/ads/my/campaigns/{campaign['id']}",
        json={"name": "Renamed draft"},
        headers=_as(OWNER),
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed draft"
    assert renamed.json()["price_paise"] == rebudgeted["price_paise"]


async def test_patch_nondraft_409(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)

    db_campaign = await session.get(Campaign, uuid.UUID(campaign["id"]))
    assert db_campaign is not None
    db_campaign.status = "active"
    await session.flush()

    resp = await client.patch(
        f"/ads/my/campaigns/{campaign['id']}", json={"name": "too late"}, headers=_as(OWNER)
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "not_editable"


async def test_client_cannot_set_price(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    business_id = await _business(session)

    body = {
        **_quote_body(),
        "business_id": str(business_id),
        "name": "Sneaky",
        "price_paise": 1,
    }
    resp = await client.post("/ads/my/campaigns", json=body, headers=_as(OWNER))
    assert resp.status_code == 422


async def test_unknown_slot_key_422_matches_admin_wire_contract(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """The self-serve surface must speak the same error contract as the
    sibling admin route (modules/ads/admin_router.create_placement, pinned by
    tests/test_ads_admin.py): `detail == "unknown_slot_key"`, an exact
    string - not a pydantic structured error list."""
    client, session = api
    await _enable_ads(session)
    business_id = await _business(session)
    bad_slot_body = _quote_body(slot_keys=["not_a_real_slot"])

    quote_resp = await client.post("/ads/my/quote", json=bad_slot_body, headers=_as(OWNER))
    assert quote_resp.status_code == 422
    assert quote_resp.json()["detail"] == "unknown_slot_key"

    create_body = {**bad_slot_body, "business_id": str(business_id), "name": "Bad slot"}
    create_resp = await client.post("/ads/my/campaigns", json=create_body, headers=_as(OWNER))
    assert create_resp.status_code == 422
    assert create_resp.json()["detail"] == "unknown_slot_key"


async def test_categories_in_geo_target_rejected_422(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """`categories` is a top-level wizard field that lands inside
    Placement.geo_target on create (selfserve_router._merge_geo_target); a
    client also populating geo_target.categories directly is an ambiguous
    wire contract (it would be silently clobbered) and must be rejected."""
    client, session = api
    await _enable_ads(session)
    business_id = await _business(session)
    dual_categories_body = _quote_body(geo_target={"categories": ["paneer"]}, categories=["ghee"])

    quote_resp = await client.post("/ads/my/quote", json=dual_categories_body, headers=_as(OWNER))
    assert quote_resp.status_code == 422
    assert quote_resp.json()["detail"] == "categories_in_geo_target"

    create_body = {
        **dual_categories_body,
        "business_id": str(business_id),
        "name": "Dual categories",
    }
    create_resp = await client.post("/ads/my/campaigns", json=create_body, headers=_as(OWNER))
    assert create_resp.status_code == 422
    assert create_resp.json()["detail"] == "categories_in_geo_target"

    # same ambiguity on PATCH
    campaign = await _create_draft(client, session)
    patch_resp = await client.patch(
        f"/ads/my/campaigns/{campaign['id']}",
        json={"geo_target": {"categories": ["paneer"]}},
        headers=_as(OWNER),
    )
    assert patch_resp.status_code == 422
    assert patch_resp.json()["detail"] == "categories_in_geo_target"
