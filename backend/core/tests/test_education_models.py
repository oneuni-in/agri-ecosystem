"""education engine ORM: the five tables of spec section 4 exist, and app_rt cannot write.

Note which session each test takes. `education` grants app_rt SELECT and
nothing else, so anything that WRITES a row takes `owner_session` -- the role
the importer runs as. Reads take `db_session`, the app's real runtime
identity, because proving the read works under app_rt is the point of having
two roles at all.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from modules.education.models import (
    Guide,
    Institution,
    InstitutionProgramme,
    Programme,
    StudentResource,
)


async def test_all_five_tables_exist(db_session: AsyncSession) -> None:
    for model in (Institution, Programme, InstitutionProgramme, StudentResource, Guide):
        # A select against an absent table raises; reaching 0 rows proves it is
        # there AND that app_rt can read it.
        assert await db_session.scalar(select(model).limit(1)) is None


async def test_institution_slug_is_unique(owner_session: AsyncSession) -> None:
    def _row(name: str) -> Institution:
        return Institution(
            slug="tnau-coimbatore",
            name_en=name,
            kind="state_agri_university",
            country_code="IN",
            trust="verified",
            status="active",
            source_url="https://tnau.ac.in/",
            last_verified_at=date(2026, 8, 10),
        )

    owner_session.add(_row("TNAU"))
    await owner_session.flush()
    owner_session.add(_row("Duplicate"))
    with pytest.raises(IntegrityError):
        await owner_session.flush()


async def test_state_id_is_a_real_foreign_key(owner_session: AsyncSession) -> None:
    """Spec section 4 asks for an FK into geo.states, and this is the half of
    the state/district asymmetry that CAN be constrained: all 36 states are
    loaded, so the constraint never rejects a valid row.

    district_id deliberately has no FK (geo.districts is Tamil Nadu only until
    D65), which is why only this one is asserted here.
    """
    owner_session.add(
        Institution(
            slug="fk-check-college",
            name_en="FK Check",
            kind="affiliated_college",
            country_code="IN",
            state_id=uuid.uuid4(),  # no such state
            trust="listed",
            status="active",
            source_url="https://example.ac.in/",
            last_verified_at=date(2026, 8, 10),
        )
    )
    with pytest.raises(IntegrityError) as excinfo:
        await owner_session.flush()
    assert "foreign key" in str(excinfo.value).lower()


async def test_district_id_is_deliberately_not_a_foreign_key(
    owner_session: AsyncSession,
) -> None:
    """The other half of the asymmetry, asserted so nobody "fixes" it.

    geo.districts is Tamil Nadu only until D65. A constraint here would
    reject a valid Punjab college, so district_id holds the LGD code as a
    plain integer and an unknown one is accepted.
    """
    owner_session.add(
        Institution(
            slug="punjab-college",
            name_en="Punjab College of Agriculture",
            kind="affiliated_college",
            country_code="IN",
            district_id=99999,  # no such district row, and that is allowed
            trust="listed",
            status="active",
            source_url="https://example.ac.in/",
            last_verified_at=date(2026, 8, 10),
        )
    )
    await owner_session.flush()  # must not raise


async def test_app_rt_cannot_write_to_education(database_url: str) -> None:
    """Spec section 4: app_rt is SELECT-only here, unlike every other schema.

    `database_url` is already the app_rt runtime URL for the test database --
    the same identity the running app uses.
    """
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            with pytest.raises(ProgrammingError) as excinfo:
                await conn.execute(
                    text(
                        "INSERT INTO education.institutions "
                        "(id, slug, name_en, kind, country_code, trust, status, "
                        " source_url, last_verified_at) "
                        "VALUES (gen_random_uuid(), 'x', 'x', 'x', 'IN', 'listed', "
                        "'active', 'https://x', '2026-01-01')"
                    )
                )
            assert "permission denied" in str(excinfo.value).lower()
    finally:
        await engine.dispose()


async def test_app_rt_cannot_write_to_any_education_table(database_url: str) -> None:
    """One table proving the grant is not enough -- 0049 grants five times,
    and a missed line would leave exactly one table writable."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            for table in (
                "programmes",
                "institution_programmes",
                "student_resources",
                "guides",
            ):
                with pytest.raises(ProgrammingError) as excinfo:
                    await conn.execute(text(f"DELETE FROM education.{table}"))
                assert "permission denied" in str(excinfo.value).lower(), table
                await conn.rollback()
    finally:
        await engine.dispose()
