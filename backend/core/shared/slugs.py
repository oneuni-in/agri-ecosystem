"""Immutable public slugs.

Slugs are the only URL-facing identifiers (never UUIDs) and are write-once:
mutating a persisted slug raises ImmutableSlugError. The sole sanctioned
path is change_slug(), which records a 301 redirect (served by
shared.middleware.SlugRedirectMiddleware) in the same transaction.
"""

from contextvars import ContextVar
from typing import Any

from sqlalchemy import Text, event, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from shared.db import Base, TimestampMixin, UUIDv7PKMixin

_sanctioned_change: ContextVar[bool] = ContextVar("sanctioned_slug_change", default=False)


class ImmutableSlugError(RuntimeError):
    """A persisted slug was mutated outside change_slug()."""


class ImmutableSlugMixin:
    slug: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)


class SlugRedirect(UUIDv7PKMixin, TimestampMixin, Base):
    """public.slug_redirects: old public path -> current public path."""

    __tablename__ = "slug_redirects"

    old_path: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    new_path: Mapped[str] = mapped_column(Text, nullable=False)


def _guard_slug_set(target: object, value: str, oldvalue: object, initiator: object) -> str:
    state = inspect(target)
    is_persisted = getattr(state, "key", None) is not None
    if (
        is_persisted
        and isinstance(oldvalue, str)
        and oldvalue != value
        and not _sanctioned_change.get()
    ):
        raise ImmutableSlugError(
            f"slug is write-once ({oldvalue!r} -> {value!r}); use shared.slugs.change_slug"
        )
    return value


@event.listens_for(Mapper, "mapper_configured")
def _install_slug_guard(mapper: Mapper[Any], cls: type) -> None:
    if issubclass(cls, ImmutableSlugMixin) and "slug" in mapper.attrs:
        event.listen(mapper.attrs["slug"].class_attribute, "set", _guard_slug_set, retval=True)


def change_slug(
    session: AsyncSession,
    instance: ImmutableSlugMixin,
    new_slug: str,
    *,
    old_path: str,
    new_path: str,
) -> None:
    """Sanctioned slug change: update the slug and record the 301 in one unit."""
    session.add(SlugRedirect(old_path=old_path, new_path=new_path))
    token = _sanctioned_change.set(True)
    try:
        instance.slug = new_slug
    finally:
        _sanctioned_change.reset(token)


async def find_redirect(session: AsyncSession, path: str) -> str | None:
    result = await session.scalars(
        select(SlugRedirect.new_path).where(SlugRedirect.old_path == path)
    )
    return result.first()
