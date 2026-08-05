"""M5 Task 6: advertiser self-serve campaign API. NN4 is the point of this
file - `_owned_campaign` must 404 (never 403) on every read/write that isn't
the caller's own business, so ownership can never be used as an oracle.

Task 8 extends this suite with self-serve creative upload + edit-triggered
re-moderation (threat: edit-after-approve bypass - an advertiser must not be
able to swap an approved creative's copy/media/link without re-entering the
moderation queue, nor keep an already-live campaign serving the swapped
content in the meantime)."""

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from typing import Any

import httpx
import pytest
from PIL import Image
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ads.models import Campaign, Creative
from modules.directory import service as directory_service
from shared.flags import FeatureFlag, reset_flag_cache
from shared.lookups import register_servable_resolver
from tests.d26_helpers import _as, api  # noqa: F401 (pytest fixture injection)
from tests.test_ads_serve import ads_redis  # noqa: F401 (pytest fixture injection)

pytestmark = pytest.mark.asyncio

OWNER = uuid.uuid4()
STRANGER = uuid.uuid4()
PINCODE = "641001"


def _jpeg_bytes(size: tuple[int, int] = (32, 32)) -> bytes:
    img = Image.new("RGB", size, "green")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


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
        ("POST", f"/ads/my/campaigns/{campaign_id}/checkout-request", {}),
        ("POST", f"/ads/my/campaigns/{campaign_id}/pause", {}),
        ("POST", f"/ads/my/campaigns/{campaign_id}/resume", {}),
        (
            "POST",
            f"/ads/my/campaigns/{campaign_id}/creatives",
            {"data": {"copy_json": "{}", "target_url": "https://example.com"}},
        ),
        (
            "PATCH",
            f"/ads/my/creatives/{uuid.uuid4()}",
            {"data": {"target_url": "https://example.com"}},
        ),
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


# ---------------------------------------------------------------------------
# Task 7: checkout-request / pause / resume


async def _add_creative(
    session: AsyncSession, campaign_id: uuid.UUID, *, status: str = "pending"
) -> Creative:
    """Self-serve creative upload is Task 8's job; these tests only need a
    creative row to exist, so it is seeded directly."""
    creative = Creative(
        campaign_id=campaign_id,
        media_keys=["ads/x.jpg"],
        copy={"en": {"title": "t", "body": "b"}},
        target_url="https://example.com",
    )
    session.add(creative)
    await session.flush()
    creative.moderation_status = status
    await session.flush()
    return creative


async def test_checkout_request_happy_path_moves_to_pending_payment(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)
    await _add_creative(session, uuid.UUID(campaign["id"]))

    resp = await client.post(
        f"/ads/my/campaigns/{campaign['id']}/checkout-request", headers=_as(OWNER)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending_payment"
    assert body["display_status"] == "pending_payment"


async def test_checkout_request_without_creative_409(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)

    resp = await client.post(
        f"/ads/my/campaigns/{campaign['id']}/checkout-request", headers=_as(OWNER)
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "no_creatives"


async def test_checkout_request_non_draft_409_not_payable(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)
    await _add_creative(session, uuid.UUID(campaign["id"]))

    first = await client.post(
        f"/ads/my/campaigns/{campaign['id']}/checkout-request", headers=_as(OWNER)
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        f"/ads/my/campaigns/{campaign['id']}/checkout-request", headers=_as(OWNER)
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "not_payable"


async def test_pause_then_resume_paid_and_approved_campaign_reactivates(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)
    await _add_creative(session, uuid.UUID(campaign["id"]), status="approved")

    db_campaign = await session.get(Campaign, uuid.UUID(campaign["id"]))
    assert db_campaign is not None
    db_campaign.status = "active"
    db_campaign.paid_at = datetime.now(UTC)
    await session.flush()

    paused = await client.post(f"/ads/my/campaigns/{campaign['id']}/pause", headers=_as(OWNER))
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "paused"

    # not-active anymore: a second pause is a 409
    conflict = await client.post(f"/ads/my/campaigns/{campaign['id']}/pause", headers=_as(OWNER))
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "not_active"

    resumed = await client.post(f"/ads/my/campaigns/{campaign['id']}/resume", headers=_as(OWNER))
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "active"


async def test_resume_with_pending_creative_falls_back_to_pending_moderation(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)
    await _add_creative(session, uuid.UUID(campaign["id"]), status="pending")

    db_campaign = await session.get(Campaign, uuid.UUID(campaign["id"]))
    assert db_campaign is not None
    db_campaign.status = "paused"
    db_campaign.paid_at = datetime.now(UTC)
    await session.flush()

    resumed = await client.post(f"/ads/my/campaigns/{campaign['id']}/resume", headers=_as(OWNER))
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "pending_moderation"


async def test_resume_past_flight_end_409_flight_over(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)

    db_campaign = await session.get(Campaign, uuid.UUID(campaign["id"]))
    assert db_campaign is not None
    db_campaign.status = "paused"
    db_campaign.flight_start = date.today() - timedelta(days=10)
    db_campaign.flight_end = date.today() - timedelta(days=1)
    await session.flush()

    resp = await client.post(f"/ads/my/campaigns/{campaign['id']}/resume", headers=_as(OWNER))
    assert resp.status_code == 409
    assert resp.json()["detail"] == "flight_over"


async def test_resume_not_paused_409(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)  # status == draft

    resp = await client.post(f"/ads/my/campaigns/{campaign['id']}/resume", headers=_as(OWNER))
    assert resp.status_code == 409
    assert resp.json()["detail"] == "not_paused"


async def test_resume_business_not_servable_409(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """THREAT: an owner must not be able to undo a staff enforcement pause
    (pause_campaigns_for_business) just by hitting resume - is_servable is
    the same fail-closed M1.5.E check the serve path uses."""
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)
    await _add_creative(session, uuid.UUID(campaign["id"]), status="approved")

    db_campaign = await session.get(Campaign, uuid.UUID(campaign["id"]))
    assert db_campaign is not None
    db_campaign.status = "paused"
    db_campaign.paid_at = datetime.now(UTC)
    await session.flush()

    async def _not_servable(session: AsyncSession, business_id: uuid.UUID) -> bool:
        return False

    register_servable_resolver(_not_servable)  # after create_app(): D20 pattern

    resp = await client.post(f"/ads/my/campaigns/{campaign['id']}/resume", headers=_as(OWNER))
    assert resp.status_code == 409
    assert resp.json()["detail"] == "business_not_servable"


async def test_lifecycle_routes_404_for_foreign_owner(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session, owner=OWNER)

    for path in (
        f"/ads/my/campaigns/{campaign['id']}/checkout-request",
        f"/ads/my/campaigns/{campaign['id']}/pause",
        f"/ads/my/campaigns/{campaign['id']}/resume",
    ):
        resp = await client.post(path, headers=_as(STRANGER))
        assert resp.status_code == 404, (path, resp.text)


# ---------------------------------------------------------------------------
# Task 8: self-serve creative upload + edit-triggered re-moderation


def _copy_json(title: str = "Kharif seeds now live", body: str = "Book your order today.") -> str:
    return json.dumps({"en": {"title": title, "body": body}})


async def test_upload_creative_happy_path(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)

    resp = await client.post(
        f"/ads/my/campaigns/{campaign['id']}/creatives",
        data={"copy_json": _copy_json(), "target_url": "https://kovaimills.example.com/offers"},
        files={"file": ("ad.jpg", _jpeg_bytes(), "image/jpeg")},
        headers=_as(OWNER),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["moderation_status"] == "pending"
    assert body["target_url"] == "https://kovaimills.example.com/offers"
    assert body["copy"]["en"]["title"] == "Kharif seeds now live"
    assert len(body["media_urls"]) == 1

    assert len(object_store) == 1
    (key,) = object_store
    assert key.startswith("ads/")
    assert key.endswith(".jpg")

    campaign_check = await client.get(f"/ads/my/campaigns/{campaign['id']}", headers=_as(OWNER))
    assert campaign_check.status_code == 200
    assert len(campaign_check.json()["creatives"]) == 1
    assert campaign_check.json()["creatives"][0]["id"] == body["id"]


async def test_upload_creative_without_image_ok(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)

    resp = await client.post(
        f"/ads/my/campaigns/{campaign['id']}/creatives",
        data={"copy_json": _copy_json(), "target_url": "https://example.com/offers"},
        headers=_as(OWNER),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["media_urls"] == []
    assert not object_store


async def test_upload_creative_rejects_too_large(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)
    oversized = b"\xff\xd8\xff" + b"0" * (6 * 1024 * 1024)  # 6 MiB, over the 5 MiB cap

    resp = await client.post(
        f"/ads/my/campaigns/{campaign['id']}/creatives",
        data={"copy_json": _copy_json(), "target_url": "https://example.com/offers"},
        files={"file": ("ad.jpg", oversized, "image/jpeg")},
        headers=_as(OWNER),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "too_large"
    assert not object_store


async def test_upload_creative_rejects_unsupported_type(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)

    resp = await client.post(
        f"/ads/my/campaigns/{campaign['id']}/creatives",
        data={"copy_json": _copy_json(), "target_url": "https://example.com/offers"},
        files={"file": ("notes.txt", b"just some text", "text/plain")},
        headers=_as(OWNER),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "unsupported_type"
    assert not object_store


async def test_upload_creative_rejects_bad_copy_json(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)

    not_json = await client.post(
        f"/ads/my/campaigns/{campaign['id']}/creatives",
        data={"copy_json": "{not json", "target_url": "https://example.com/offers"},
        headers=_as(OWNER),
    )
    assert not_json.status_code == 422
    assert not_json.json()["detail"] == "invalid_copy_json"

    missing_en = await client.post(
        f"/ads/my/campaigns/{campaign['id']}/creatives",
        data={
            "copy_json": json.dumps({"ta": {"title": "t", "body": "b"}}),
            "target_url": "https://example.com/offers",
        },
        headers=_as(OWNER),
    )
    assert missing_en.status_code == 422
    assert missing_en.json()["detail"] == "invalid_copy_json"


async def test_upload_creative_rejects_bad_target_url(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)

    resp = await client.post(
        f"/ads/my/campaigns/{campaign['id']}/creatives",
        data={"copy_json": _copy_json(), "target_url": "javascript:alert(1)"},
        headers=_as(OWNER),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "invalid_target_url"


async def test_creative_limit_409(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)
    for i in range(5):
        resp = await client.post(
            f"/ads/my/campaigns/{campaign['id']}/creatives",
            data={"copy_json": _copy_json(f"Ad {i}"), "target_url": "https://example.com/offers"},
            headers=_as(OWNER),
        )
        assert resp.status_code == 201, resp.text

    sixth = await client.post(
        f"/ads/my/campaigns/{campaign['id']}/creatives",
        data={"copy_json": _copy_json("One too many"), "target_url": "https://example.com/offers"},
        headers=_as(OWNER),
    )
    assert sixth.status_code == 409
    assert sixth.json()["detail"] == "creative_limit"


async def test_upload_creative_non_editable_campaign_409(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)
    db_campaign = await session.get(Campaign, uuid.UUID(campaign["id"]))
    assert db_campaign is not None
    db_campaign.status = "archived"
    await session.flush()

    resp = await client.post(
        f"/ads/my/campaigns/{campaign['id']}/creatives",
        data={"copy_json": _copy_json(), "target_url": "https://example.com/offers"},
        headers=_as(OWNER),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "not_editable"


async def test_upload_creative_foreign_campaign_404(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session, owner=OWNER)

    resp = await client.post(
        f"/ads/my/campaigns/{campaign['id']}/creatives",
        data={"copy_json": _copy_json(), "target_url": "https://example.com/offers"},
        headers=_as(STRANGER),
    )
    assert resp.status_code == 404
    assert not object_store


async def _upload_creative(
    client: httpx.AsyncClient, campaign_id: str, *, owner: uuid.UUID = OWNER
) -> dict[str, Any]:
    resp = await client.post(
        f"/ads/my/campaigns/{campaign_id}/creatives",
        data={"copy_json": _copy_json(), "target_url": "https://example.com/offers"},
        headers=_as(owner),
    )
    assert resp.status_code == 201, resp.text
    result: dict[str, Any] = resp.json()
    return result


async def test_patch_creative_updates_copy_and_target_url(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)
    creative = await _upload_creative(client, campaign["id"])

    resp = await client.patch(
        f"/ads/my/creatives/{creative['id']}",
        data={
            "copy_json": _copy_json("Updated title"),
            "target_url": "https://kovaimills.example.com/new-offer",
        },
        headers=_as(OWNER),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["copy"]["en"]["title"] == "Updated title"
    assert body["target_url"] == "https://kovaimills.example.com/new-offer"
    assert body["moderation_status"] == "pending"


async def test_patch_creative_foreign_owner_404(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session, owner=OWNER)
    creative = await _upload_creative(client, campaign["id"], owner=OWNER)

    resp = await client.patch(
        f"/ads/my/creatives/{creative['id']}",
        data={"target_url": "https://evil.example.com"},
        headers=_as(STRANGER),
    )
    assert resp.status_code == 404

    check = await client.get(f"/ads/my/campaigns/{campaign['id']}", headers=_as(OWNER))
    assert (
        check.json()["creatives"][0]["target_url"] == "https://example.com/offers"
    )  # untouched by the foreign attempt

    unknown = await client.patch(
        f"/ads/my/creatives/{uuid.uuid4()}",
        data={"target_url": "https://evil.example.com"},
        headers=_as(OWNER),
    )
    assert unknown.status_code == 404


async def test_edit_approved_creative_on_active_campaign_repends_and_demotes(
    api: tuple[httpx.AsyncClient, AsyncSession],
    object_store: dict[str, bytes],
    ads_redis: Redis,
) -> None:
    """THREAT (edit-after-approve bypass, spec non-negotiable): swapping an
    approved creative's content on a LIVE campaign must both (a) re-enter
    moderation and (b) stop the campaign from serving until it clears again -
    otherwise an advertiser could get one creative approved then silently
    swap in unapproved content/links behind the moderation queue's back."""
    client, session = api
    await _enable_ads(session)
    today = date.today()
    campaign = await _create_draft(
        client,
        session,
        geo_target={},
        categories=[],
        # _quote_body's default flight_start is TOMORROW (draft-creation
        # premise) - the serve path requires flight_start <= today, so this
        # test (which needs the campaign live-and-serving) backdates it.
        flight_start=(today - timedelta(days=1)).isoformat(),
        flight_end=(today + timedelta(days=30)).isoformat(),
    )
    creative = await _upload_creative(client, campaign["id"])

    # approve directly - moderation approval itself is the ops module's job
    # (Task 7/ops), out of scope here; this suite only needs an approved row.
    db_creative = await session.get(Creative, uuid.UUID(creative["id"]))
    assert db_creative is not None
    db_creative.moderation_status = "approved"
    await session.flush()

    # activate the campaign directly (payment + moderation gate is Task 7's
    # lifecycle engine, already covered by test_ads_lifecycle.py)
    db_campaign = await session.get(Campaign, uuid.UUID(campaign["id"]))
    assert db_campaign is not None
    db_campaign.status = "active"
    db_campaign.paid_at = datetime.now(UTC)
    await session.flush()

    before = await client.get("/ads/serve", params={"slot": "milk_home_hero"})
    assert before.status_code == 200, before.text
    assert before.json()["ad"] is not None
    assert before.json()["ad"]["creative_id"] == creative["id"]

    patch_resp = await client.patch(
        f"/ads/my/creatives/{creative['id']}",
        data={"copy_json": _copy_json("Swapped copy after approval")},
        headers=_as(OWNER),
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["moderation_status"] == "pending"

    await session.refresh(db_creative)
    assert db_creative.moderation_status == "pending"
    await session.refresh(db_campaign)
    assert db_campaign.status == "pending_moderation"

    after = await client.get("/ads/serve", params={"slot": "milk_home_hero"})
    assert after.status_code == 200, after.text
    assert after.json() == {"ad": None, "ads": []}


async def test_edit_creative_on_draft_campaign_only_repends_no_demote(
    api: tuple[httpx.AsyncClient, AsyncSession], object_store: dict[str, bytes]
) -> None:
    """A draft campaign has nothing to demote (it was never active) - the
    edit must still re-pend the creative, but demote_to_moderation is a
    documented no-op off `active`."""
    client, session = api
    await _enable_ads(session)
    campaign = await _create_draft(client, session)
    creative = await _upload_creative(client, campaign["id"])

    db_creative = await session.get(Creative, uuid.UUID(creative["id"]))
    assert db_creative is not None
    db_creative.moderation_status = "approved"
    await session.flush()

    resp = await client.patch(
        f"/ads/my/creatives/{creative['id']}",
        data={"target_url": "https://kovaimills.example.com/new-offer"},
        headers=_as(OWNER),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["moderation_status"] == "pending"

    check = await client.get(f"/ads/my/campaigns/{campaign['id']}", headers=_as(OWNER))
    assert check.json()["status"] == "draft"  # unchanged - nothing to demote
