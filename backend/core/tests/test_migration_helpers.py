"""shared/migrations.py: standard mixin columns for hand-written migrations,
so op.create_table never omits the one-way-door columns."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from shared.migrations import (
    pk_column,
    soft_delete_column,
    timestamp_columns,
    ugc_column,
)


def test_pk_column_is_uuid_primary_key() -> None:
    column = pk_column()
    assert column.name == "id"
    assert column.primary_key is True
    assert isinstance(column.type, postgresql.UUID)


def test_timestamp_columns_are_timestamptz_with_server_defaults() -> None:
    created, updated = timestamp_columns()
    assert (created.name, updated.name) == ("created_at", "updated_at")
    for column in (created, updated):
        assert isinstance(column.type, sa.TIMESTAMP)
        assert column.type.timezone is True
        assert column.server_default is not None
        assert column.nullable is False


def test_soft_delete_column_is_nullable_timestamptz() -> None:
    column = soft_delete_column()
    assert column.name == "deleted_at"
    assert isinstance(column.type, sa.TIMESTAMP)
    assert column.type.timezone is True
    assert column.nullable is True


def test_ugc_column_defaults_to_pending() -> None:
    column = ugc_column()
    assert column.name == "moderation_status"
    assert isinstance(column.type, postgresql.ENUM)
    assert column.type.name == "moderation_status"
    assert column.type.create_type is False
    assert column.server_default is not None
    assert column.nullable is False


def test_helpers_return_fresh_columns_each_call() -> None:
    # sa.Column objects can only be attached to one table
    assert pk_column() is not pk_column()
    assert timestamp_columns()[0] is not timestamp_columns()[0]
