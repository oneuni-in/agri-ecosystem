"""Async SQLAlchemy engine, session factory, declarative base, and the D03
one-way-door mixins: UUIDv7 PKs, UTC audit timestamps, default-filtered
soft-delete, and pending-by-default moderation for user-generated content.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import uuid6
from sqlalchemy import TIMESTAMP, MetaData, event, func, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    ORMExecuteState,
    Session,
    mapped_column,
    with_loader_criteria,
)

from settings import get_settings

# Deterministic constraint names so autogenerate never churns and
# downgrades can always find what they created.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDv7PKMixin:
    """Time-ordered UUIDv7 primary key, generated client-side (PG16 has no uuidv7())."""

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), primary_key=True, default=uuid6.uuid7
    )


class TimestampMixin:
    """created_at/updated_at as timestamptz with server defaults - never naive."""

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    # clock_timestamp() (not now()) so updates inside one transaction still bump it
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.clock_timestamp(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Nullable deleted_at; rows with a value are invisible to ORM selects by
    default (see _filter_soft_deleted). Opt out per-statement with
    .execution_options(include_deleted=True) - justify every use in review."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, default=None
    )


class UGCMixin:
    """User-generated content starts life unpublished."""

    moderation_status: Mapped[str] = mapped_column(
        postgresql.ENUM(
            "pending",
            "approved",
            "rejected",
            name="moderation_status",
            schema="public",
            create_type=False,
        ),
        server_default=text("'pending'"),
        nullable=False,
    )


def soft_delete(instance: SoftDeleteMixin) -> None:
    instance.deleted_at = datetime.now(UTC)


@event.listens_for(Session, "do_orm_execute")
def _filter_soft_deleted(execute_state: ORMExecuteState) -> None:
    if (
        execute_state.is_select
        and not execute_state.is_column_load
        and not execute_state.is_relationship_load
        and not execute_state.execution_options.get("include_deleted", False)
    ):
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                SoftDeleteMixin,
                lambda cls: cls.deleted_at.is_(None),
                include_aliases=True,
            )
        )


_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url)
    return _engine


def reset_engine() -> None:
    """Drop the singleton so the next call rebuilds from current settings (tests)."""
    global _engine
    _engine = None


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, committed on success.

    An exception escaping the endpoint skips the commit; closing the session
    rolls the transaction back."""
    async with get_sessionmaker()() as session:
        yield session
        await session.commit()


async def check_database() -> bool:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
