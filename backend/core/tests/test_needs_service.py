"""Needs service (D25): fan-out routing to covering vendors only
(non-negotiable 1, pincode 641001), ownership IDOR, child bookkeeping."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from modules.directory import leads_service, needs_service, service
from modules.directory.leads_models import Inquiry, Need
from modules.directory.models import Business

pytestmark = pytest.mark.asyncio

PINCODE = "641001"  # non-negotiable 1 mandates this exact pincode
OTHER_PINCODE = "600001"


def _owner_of(business: Business) -> uuid.UUID:
    assert business.owner_user_id is not None
    return business.owner_user_id


async def _mk_business_with_coverage(
    session: AsyncSession, pincode: str, name: str = "Vendor"
) -> Business:
    owner = uuid.uuid4()
    business = await service.create_business(
        session, owner_user_id=owner, name=name, type_="vendor", primary_pincode=pincode
    )
    await service.set_coverage(
        session, owner_user_id=owner, business_id=business.id, pincodes=[pincode]
    )
    return business


async def test_route_need_fans_out_to_all_covering(
    db_session: AsyncSession, tn_geo_sample: None
) -> None:
    a = await _mk_business_with_coverage(db_session, PINCODE, name="A")
    b = await _mk_business_with_coverage(db_session, PINCODE, name="B")
    await _mk_business_with_coverage(db_session, OTHER_PINCODE, name="C")
    vendors = await needs_service.route_need(db_session, pincode=PINCODE)
    assert {v.id for v in vendors} == {a.id, b.id}  # C never routed
    owners = {v.id: v.owner_user_id for v in vendors}
    assert owners[a.id] == _owner_of(a)


async def test_route_need_respects_fanout_limit(
    db_session: AsyncSession, tn_geo_sample: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    for i in range(3):
        await _mk_business_with_coverage(db_session, PINCODE, name=f"V{i}")
    monkeypatch.setattr(needs_service, "_fanout_limit", lambda: 2)
    vendors = await needs_service.route_need(db_session, pincode=PINCODE)
    assert len(vendors) == 2


async def test_route_need_no_coverage_raises(db_session: AsyncSession, tn_geo_sample: None) -> None:
    with pytest.raises(leads_service.NoCoverageError):
        await needs_service.route_need(db_session, pincode="999999")


async def test_get_owned_need_idor(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    need = Need(from_user_id=owner, pincode=PINCODE, payload={})
    db_session.add(need)
    await db_session.flush()
    got = await needs_service.get_owned_need(db_session, owner, need.id)
    assert got.id == need.id
    with pytest.raises(needs_service.NeedNotFoundError):
        await needs_service.get_owned_need(db_session, uuid.uuid4(), need.id)


async def test_close_open_children_leaves_closed_alone(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    need = Need(from_user_id=owner, pincode=PINCODE, payload={})
    db_session.add(need)
    await db_session.flush()
    open_child = Inquiry(
        type="milk_subscription",
        from_user_id=owner,
        business_id=uuid.uuid4(),
        payload={},
        pincode=PINCODE,
        need_id=need.id,
    )
    responded_child = Inquiry(
        type="milk_subscription",
        from_user_id=owner,
        business_id=uuid.uuid4(),
        payload={},
        pincode=PINCODE,
        need_id=need.id,
        status="responded",
    )
    unrelated = Inquiry(
        type="contact",
        from_user_id=owner,
        business_id=uuid.uuid4(),
        payload={},
        pincode=PINCODE,
    )
    db_session.add_all([open_child, responded_child, unrelated])
    await db_session.flush()
    await needs_service.close_open_children(db_session, need.id)
    for child in (open_child, responded_child, unrelated):
        await db_session.refresh(child)
    assert open_child.status == "closed"
    assert responded_child.status == "closed"
    assert unrelated.status == "new"  # not a child of this need
