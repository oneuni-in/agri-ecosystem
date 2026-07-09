"""Immutable slugs: write-once guard, sanctioned change path recording a
redirect, and the 301 middleware that serves old paths."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base, TimestampMixin, UUIDv7PKMixin
from shared.middleware import SlugRedirectMiddleware
from shared.slugs import (
    ImmutableSlugError,
    ImmutableSlugMixin,
    SlugRedirect,
    change_slug,
    find_redirect,
)


class SluggedPost(ImmutableSlugMixin, UUIDv7PKMixin, TimestampMixin, Base):
    __tablename__ = "test_slugged_posts"
    __table_args__ = {"schema": "content"}

    title: Mapped[str] = mapped_column()


async def _create_tables(session: AsyncSession) -> None:
    conn = await session.connection()
    tables = [
        Base.metadata.tables["content.test_slugged_posts"],
        Base.metadata.tables["slug_redirects"],
    ]
    await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))


async def test_slug_is_write_once_on_persisted_rows(db_session: AsyncSession) -> None:
    await _create_tables(db_session)
    post = SluggedPost(slug="first-slug", title="t")
    db_session.add(post)
    await db_session.flush()

    with pytest.raises(ImmutableSlugError):
        post.slug = "second-slug"


async def test_slug_is_settable_before_first_flush(db_session: AsyncSession) -> None:
    await _create_tables(db_session)
    post = SluggedPost(slug="draft-slug", title="t")
    post.slug = "final-slug"  # still transient - allowed
    db_session.add(post)
    await db_session.flush()
    assert post.slug == "final-slug"


async def test_change_slug_is_sanctioned_and_records_redirect(db_session: AsyncSession) -> None:
    await _create_tables(db_session)
    post = SluggedPost(slug="old-name", title="t")
    db_session.add(post)
    await db_session.flush()

    change_slug(
        db_session, post, "new-name", old_path="/posts/old-name", new_path="/posts/new-name"
    )
    await db_session.flush()

    assert post.slug == "new-name"
    redirect = (await db_session.scalars(select(SlugRedirect))).one()
    assert (redirect.old_path, redirect.new_path) == ("/posts/old-name", "/posts/new-name")


async def test_find_redirect_returns_new_path_or_none(db_session: AsyncSession) -> None:
    await _create_tables(db_session)
    db_session.add(SlugRedirect(old_path="/posts/old-name", new_path="/posts/new-name"))
    await db_session.flush()

    assert await find_redirect(db_session, "/posts/old-name") == "/posts/new-name"
    assert await find_redirect(db_session, "/posts/never-existed") is None


def _make_app(redirects: dict[str, str]) -> TestClient:
    app = FastAPI()

    @app.get("/exists")
    def exists() -> dict[str, str]:
        return {"status": "ok"}

    async def lookup(path: str) -> str | None:
        return redirects.get(path)

    app.add_middleware(SlugRedirectMiddleware, lookup=lookup)
    return TestClient(app, follow_redirects=False)


def test_middleware_301s_known_old_paths() -> None:
    client = _make_app({"/posts/old-name": "/posts/new-name"})
    response = client.get("/posts/old-name")
    assert response.status_code == 301
    assert response.headers["location"] == "/posts/new-name"


def test_middleware_leaves_real_404s_alone() -> None:
    client = _make_app({"/posts/old-name": "/posts/new-name"})
    assert client.get("/posts/never-existed").status_code == 404


def test_middleware_does_not_touch_matched_routes_or_writes() -> None:
    client = _make_app({"/exists": "/hijacked", "/posts/old-name": "/posts/new-name"})
    assert client.get("/exists").status_code == 200  # 404-only, never hijacks real routes
    assert client.post("/posts/old-name").status_code == 404  # redirects are GET/HEAD only
