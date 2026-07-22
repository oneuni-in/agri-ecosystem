import uuid

import pytest
from sqlalchemy import select

from modules.directory.leads_models import PincodeInterest


@pytest.mark.asyncio
async def test_pincode_interest_row_roundtrips(db_session):
    row = PincodeInterest(
        pincode="641001",
        district="Coimbatore",
        contact="+919876500001",
        from_user_id=None,
        milk_type="cow",
    )
    db_session.add(row)
    await db_session.flush()

    fetched = await db_session.scalar(
        select(PincodeInterest).where(PincodeInterest.id == row.id)
    )
    assert fetched is not None
    assert isinstance(fetched.id, uuid.UUID)  # UUIDv7 PK auto-assigned
    assert fetched.pincode == "641001"
    assert fetched.district == "Coimbatore"
    assert fetched.from_user_id is None
    assert fetched.created_at is not None
