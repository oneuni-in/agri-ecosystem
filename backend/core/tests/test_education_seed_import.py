"""seed_import validates through the SAME contract module the gate uses, then upserts.

Every test here takes `owner_session`: `education` grants app_rt SELECT only
(0049), and the importer runs as the table owner. A test on `db_session`
would fail with `permission denied`, which is the grant working.

`education_geo` loads the real geo snapshot first. The importer resolves
state names to `geo.states.id` through a real FK, so an empty geo table means
either a hard constraint error or 772 rows with a null state — and the second
one looks perfectly healthy until every state page comes up empty.
"""

from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from modules.education.models import Guide, Institution, InstitutionProgramme, Programme
from modules.education.seed_import import ImportReport, import_bundle
from scripts.education_seed_contract import SeedContractError
from shared.geo.loader import load_geo
from shared.geo.models import District, State

SEED = Path(__file__).resolve().parents[1] / "data" / "seeds" / "education"
GEO = Path(__file__).resolve().parents[1] / "data" / "geo"
TODAY = date(2026, 8, 17)


@pytest.fixture
async def education_geo(owner_session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """The real 36-state / 38-district snapshot, in the owner's transaction."""
    await load_geo(owner_session, GEO)
    await owner_session.flush()
    yield owner_session


@pytest.fixture
async def committed_geo(admin_database_url: str) -> AsyncIterator[None]:
    """Geo that a SEPARATE connection can see.

    The CLI tests need this and the in-process tests do not: `_main` opens its
    own engine, so anything `education_geo` wrote inside an uncommitted
    transaction is invisible to it. Committing is the only way to hand data
    across two connections, so the teardown puts the tables back the way the
    freshly-migrated database had them -- empty.
    """
    engine = create_async_engine(admin_database_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await load_geo(session, GEO)
        await session.commit()
    try:
        yield
    finally:
        async with maker() as session:
            for table in ("pincodes", "districts", "states"):
                await session.execute(text(f"DELETE FROM geo.{table}"))
            await session.commit()
        await engine.dispose()


async def test_import_loads_the_committed_bundle(education_geo: AsyncSession) -> None:
    report = await import_bundle(education_geo, SEED, GEO, today=TODAY)
    assert isinstance(report, ImportReport)
    assert report.created["institutions"] > 700
    assert (
        await education_geo.scalar(select(func.count()).select_from(Institution))
        == report.created["institutions"]
    )


async def test_import_is_idempotent(education_geo: AsyncSession) -> None:
    first = await import_bundle(education_geo, SEED, GEO, today=TODAY)
    second = await import_bundle(education_geo, SEED, GEO, today=TODAY)
    assert second.created["institutions"] == 0
    assert second.updated["institutions"] == first.created["institutions"]
    assert (
        await education_geo.scalar(select(func.count()).select_from(Institution))
        == first.created["institutions"]
    )


async def test_import_refuses_a_bundle_the_contract_rejects(
    education_geo: AsyncSession, tmp_path: Path
) -> None:
    """The importer must not hold a looser idea of valid than the gate does."""
    for name in (
        "institutions.csv",
        "programmes.csv",
        "institution_programmes.csv",
        "student_resources.csv",
        "guides.csv",
    ):
        (tmp_path / name).write_text("slug\n", encoding="utf-8")
    (tmp_path / "institutions.csv").write_text(
        "slug,name_en,kind,country_code,state,trust,status,source_url,last_verified_at\n"
        "abroad,Nowhere,nonsense,IN,Atlantis,verified,active,,\n",
        encoding="utf-8",
    )
    with pytest.raises(SeedContractError):
        await import_bundle(education_geo, tmp_path, GEO, today=TODAY)
    assert await education_geo.scalar(select(func.count()).select_from(Institution)) == 0


async def test_parent_and_programme_slugs_resolve_to_ids(education_geo: AsyncSession) -> None:
    await import_bundle(education_geo, SEED, GEO, today=TODAY)
    child = await education_geo.scalar(
        select(Institution).where(Institution.slug == "acri-coimbatore")
    )
    parent = await education_geo.scalar(
        select(Institution).where(Institution.slug == "tnau-coimbatore")
    )
    assert child is not None and parent is not None
    assert child.parent_id == parent.id
    assert await education_geo.scalar(select(func.count()).select_from(Programme)) > 40


async def test_every_institution_resolves_to_a_real_state(education_geo: AsyncSession) -> None:
    """state_id is an FK, so an unresolved state would be a constraint error --
    but a NULL is still possible when the name fails to match, and a corpus
    that imports with 772 null states looks completely healthy while every
    state page comes up empty."""
    await import_bundle(education_geo, SEED, GEO, today=TODAY)

    unresolved = await education_geo.scalar(
        select(func.count())
        .select_from(Institution)
        .where(Institution.country_code == "IN", Institution.state_id.is_(None))
    )
    assert unresolved == 0, f"{unresolved} Indian institutions imported with no state"

    # And the FK points somewhere real, not at a stale id.
    joined = await education_geo.scalar(
        select(func.count()).select_from(Institution).join(State, Institution.state_id == State.id)
    )
    assert joined is not None and joined > 700


async def test_the_seed_districts_are_not_silently_dropped(education_geo: AsyncSession) -> None:
    """70 of the 772 rows carry a district, all Tamil Nadu, and all 70 match
    geo.districts by name. An importer that never assigned district_id would
    pass every other test in this file."""
    await import_bundle(education_geo, SEED, GEO, today=TODAY)

    with_district = await education_geo.scalar(
        select(func.count()).select_from(Institution).where(Institution.district_id.is_not(None))
    )
    assert with_district is not None and with_district >= 70, (
        f"only {with_district} rows got a district_id"
    )

    # district_id holds an LGD code, NOT a geo.districts PK -- the join is on
    # lgd_code. Getting this backwards yields zero rows, not an error.
    joined = await education_geo.scalar(
        select(func.count())
        .select_from(Institution)
        .join(District, Institution.district_id == District.lgd_code)
    )
    assert joined is not None and joined >= 70


async def test_offerings_and_guides_land_with_their_own_stamps(
    education_geo: AsyncSession,
) -> None:
    """The per-offering source_url/last_verified_at is the whole reason
    institution_programmes exists as its own table (spec section 4). An
    importer that copied the institution's stamp would pass a row count."""
    await import_bundle(education_geo, SEED, GEO, today=TODAY)

    offerings = list(await education_geo.scalars(select(InstitutionProgramme)))
    assert len(offerings) > 200
    assert all(o.source_url and o.last_verified_at for o in offerings)

    guides = list(await education_geo.scalars(select(Guide)))
    assert len(guides) >= 13
    # official_links is a flat list of URL strings, not {label, url} objects.
    for guide in guides:
        assert isinstance(guide.official_links, list)
        assert all(isinstance(link, str) for link in guide.official_links or [])


async def test_the_import_refuses_to_run_against_an_empty_geo(
    owner_session: AsyncSession,
) -> None:
    """No geo, no import. The alternative is 772 rows with a null state, which
    is the failure that looks like success."""
    with pytest.raises(SeedContractError) as excinfo:
        await import_bundle(owner_session, SEED, GEO, today=TODAY)
    assert "geo.states is empty" in str(excinfo.value)


async def test_cli_dry_run_writes_nothing(
    committed_geo: None,
    education_geo: AsyncSession,
    admin_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI must connect as the OWNER, and --dry-run must leave no trace.

    DATABASE_ADMIN_URL is pointed at the test database first. Without that
    this test would run the importer against the developer's real database,
    which is how a test suite quietly rewrites someone's dev data.
    """
    from settings import get_settings

    monkeypatch.setenv("DATABASE_ADMIN_URL", admin_database_url)
    get_settings.cache_clear()

    from scripts.import_education_seed import _main

    assert await _main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "institutions" in out

    # The CLI opened its own connection and rolled it back, so this session --
    # which is a different transaction -- must see nothing.
    assert await education_geo.scalar(select(func.count()).select_from(Institution)) == 0


async def test_cli_reports_contract_violations_and_writes_nothing(
    committed_geo: None,
    education_geo: AsyncSession,
    admin_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from settings import get_settings

    monkeypatch.setenv("DATABASE_ADMIN_URL", admin_database_url)
    get_settings.cache_clear()

    for name in (
        "institutions.csv",
        "programmes.csv",
        "institution_programmes.csv",
        "student_resources.csv",
        "guides.csv",
    ):
        (tmp_path / name).write_text("slug\n", encoding="utf-8")
    (tmp_path / "institutions.csv").write_text(
        "slug,name_en,kind,country_code,state,trust,status,source_url,last_verified_at\n"
        "abroad,Nowhere,nonsense,IN,Atlantis,verified,active,,\n",
        encoding="utf-8",
    )

    from scripts.import_education_seed import _main

    assert await _main(["--seed-dir", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "CONTRACT VIOLATIONS" in out
    assert "nothing imported" in out
    assert await education_geo.scalar(select(func.count()).select_from(Institution)) == 0
