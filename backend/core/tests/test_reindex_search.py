"""D19 Task 4: full-reindex script republishes every business/product snapshot
over the bus so the search worker can rebuild indexes from Postgres truth
(ADR-0007 "indexes are rebuildable"). Reindexing must include invisible rows
(soft-deleted, pending, suspended) - the worker needs those events too, to
tombstone stale documents rather than leave them behind in the index."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import catalog_service, search_sync, service
from scripts import reindex_search

pytestmark = pytest.mark.asyncio


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, dict[str, Any]]]:
    events: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_publish(stream: str, event_type: str, payload: dict[str, Any]) -> str:
        events.append((stream, event_type, payload))
        return "1-0"

    monkeypatch.setattr(reindex_search, "publish", fake_publish)
    return events


async def test_reindex_publishes_for_all_rows(
    db_session: AsyncSession,
    tn_geo_sample: None,
    recorder: list[tuple[str, str, dict[str, Any]]],
) -> None:
    owner = uuid.uuid4()
    live = await service.create_business(
        db_session,
        owner_user_id=owner,
        name="Live Farm",
        type_="vendor",
        primary_pincode="641001",
    )
    gone = await service.create_business(
        db_session,
        owner_user_id=owner,
        name="Gone Farm",
        type_="vendor",
        primary_pincode="641001",
    )
    gone.deleted_at = datetime.now(UTC)
    await db_session.flush()
    product = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=live.id,
        vertical_slug="milk",
        name="A2 Milk 500ml",
        specs={"milk_type": "a2"},
    )

    count = await reindex_search.run(db_session)

    assert count == 3
    assert all(stream == "directory" for stream, _, _ in recorder)
    biz_events = {p["business_id"]: p for _, t, p in recorder if t == "business.updated"}
    assert set(biz_events) == {str(live.id), str(gone.id)}
    assert biz_events[str(live.id)]["snapshot"] is not None
    assert biz_events[str(gone.id)]["snapshot"] is None  # soft-deleted -> tombstone

    prod_events = [(t, p) for _, t, p in recorder if t == "product.updated"]
    assert len(prod_events) == 1
    prod_type, prod_payload = prod_events[0]
    assert prod_payload["product_id"] == str(product.id)
    assert prod_payload["business_id"] == str(live.id)
    assert prod_payload["doc_id"] == f"product_{product.id.hex}"


async def test_reindex_tolerates_soft_deleted_product(
    db_session: AsyncSession,
    tn_geo_sample: None,
    recorder: list[tuple[str, str, dict[str, Any]]],
) -> None:
    """The `assert prod is not None` guard in product_event_payload's second
    session.get() used to choke on a soft-deleted product: that lookup was
    filtered by the same soft-delete listener as everything else, so a
    genuinely soft-deleted row (as opposed to a never-existed id) came back
    None and tripped the assert instead of yielding a tombstone."""
    owner = uuid.uuid4()
    biz = await service.create_business(
        db_session,
        owner_user_id=owner,
        name="Dairy With Recalled Product",
        type_="vendor",
        primary_pincode="641001",
    )
    product = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=biz.id,
        vertical_slug="milk",
        name="Recalled Milk",
        specs={"milk_type": "cow"},
    )
    await catalog_service.moderate_product(db_session, product_id=product.id, approve=True)
    product.deleted_at = datetime.now(UTC)
    await db_session.flush()

    count = await reindex_search.run(db_session)

    assert count == 2  # 1 business + 1 (soft-deleted) product
    prod_events = [p for _, t, p in recorder if t == "product.updated"]
    assert len(prod_events) == 1
    assert prod_events[0]["doc_id"] == f"product_{product.id.hex}"
    assert prod_events[0]["product_id"] == str(product.id)
    assert prod_events[0]["business_id"] == str(biz.id)
    assert prod_events[0]["snapshot"] is None


async def test_product_event_payload_tolerates_soft_delete_directly(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    """Narrower unit test pinning the search_sync.product_event_payload fix
    itself, independent of the reindex script."""
    owner = uuid.uuid4()
    biz = await service.create_business(
        db_session,
        owner_user_id=owner,
        name="Direct Check Dairy",
        type_="vendor",
        primary_pincode="641001",
    )
    product = await catalog_service.create_product(
        db_session,
        owner_user_id=owner,
        business_id=biz.id,
        vertical_slug="milk",
        name="Direct Check Milk",
        specs={"milk_type": "cow"},
    )
    product.deleted_at = datetime.now(UTC)
    await db_session.flush()

    payload = await search_sync.product_event_payload(db_session, product.id)

    assert payload["doc_id"] == f"product_{product.id.hex}"
    assert payload["product_id"] == str(product.id)
    assert payload["business_id"] == str(biz.id)
    assert payload["snapshot"] is None
