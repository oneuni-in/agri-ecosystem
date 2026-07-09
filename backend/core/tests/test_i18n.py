"""TranslatedString: JSONB {"en","ta","hi"} with typed accessors and a
fallback chain (requested -> en -> any non-empty)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, UUIDv7PKMixin
from shared.i18n import Translated, TranslatedString


class TranslatedThing(UUIDv7PKMixin, Base):
    __tablename__ = "test_translated_things"
    __table_args__ = {"schema": "content"}

    title: Mapped[Translated] = mapped_column(TranslatedString, nullable=False)


def test_get_returns_requested_locale() -> None:
    value = Translated(en="Rice", ta="அரிசி", hi="चावल")
    assert value.get("ta") == "அரிசி"


def test_get_falls_back_to_english() -> None:
    value = Translated(en="Rice")
    assert value.get("ta") == "Rice"


def test_get_falls_back_to_any_nonempty() -> None:
    value = Translated(ta="அரிசி")
    assert value.get("hi") == "அரிசி"


def test_unknown_locale_key_rejected() -> None:
    with pytest.raises(ValueError, match="fr"):
        Translated.from_dict({"en": "Rice", "fr": "Riz"})


def test_non_string_value_rejected() -> None:
    with pytest.raises(ValueError, match="hi"):
        Translated.from_dict({"hi": 42})


def test_unknown_get_locale_rejected() -> None:
    with pytest.raises(ValueError, match="de"):
        Translated(en="Rice").get("de")


async def test_round_trips_through_jsonb(db_session: AsyncSession) -> None:
    conn = await db_session.connection()
    table = Base.metadata.tables["content.test_translated_things"]
    await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[table]))

    db_session.add(TranslatedThing(title=Translated(en="Rice", ta="அரிசி")))
    await db_session.flush()
    db_session.expunge_all()

    loaded = (await db_session.scalars(select(TranslatedThing))).one()
    assert isinstance(loaded.title, Translated)
    assert loaded.title.get("ta") == "அரிசி"
    assert loaded.title.get("hi") == "Rice"


async def test_bind_rejects_unknown_keys_from_raw_dicts(db_session: AsyncSession) -> None:
    conn = await db_session.connection()
    table = Base.metadata.tables["content.test_translated_things"]
    await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[table]))

    db_session.add(TranslatedThing(title={"en": "Rice", "fr": "Riz"}))
    with pytest.raises(Exception, match="fr"):
        await db_session.flush()
