# Backend service-layer conventions (D03)

These are the one-way doors encoded in `backend/core/shared/`. Module code
(D06+) builds on them; deviations need an explicit decision, not a local
workaround.

## Identity and time

- Every table uses the mixins from `shared/db.py`. A model that subclasses
  `UUIDv7PKMixin, TimestampMixin, SoftDeleteMixin, Base` gets a time-ordered
  UUIDv7 primary key, `created_at`/`updated_at` as `timestamptz` server
  defaults, and default-filtered soft-delete with **zero extra code**.
- Never construct naive datetimes. Use `datetime.now(UTC)`; columns are
  always `TIMESTAMP(timezone=True)`.
- UUIDs never appear in URL-facing helpers. Public identifiers are slugs
  (`shared/slugs.py`); IDs are internal.

## Listing

- `shared.pagination.paginate()` is the **only** list mechanism — admin
  included. It keysets on the UUIDv7 `id` and returns `Page[T]` with an
  opaque `next_cursor`. `OFFSET` in any form fails
  `tests/test_lint_contracts.py`.
- Do not order a query you hand to `paginate()`; it applies `ORDER BY id`
  itself.

## Ownership

- Every service query that returns user-owned rows passes through
  `shared.ownership.owned_by(query, user_id)`. It fails closed (TypeError)
  when the model lacks the ownership column, so forgetting the column is a
  test failure, not a data leak.
- The ownership column is named `owner_id` unless a module has a strong,
  documented reason otherwise (`column=` parameter).

## Soft delete

- Rows are soft-deleted with `shared.db.soft_delete(obj)`; ORM selects hide
  them automatically.
- `.execution_options(include_deleted=True)` is the only escape hatch. Every
  use carries a one-line justification comment and is expected to be rare
  (admin/moderation surfaces).

## Sessions

- Sessions are opened at the router/service boundary via
  `shared.db.get_sessionmaker()`; helpers receive an `AsyncSession`, they
  never create their own.

## User-generated content

- UGC models add `UGCMixin`; content starts `pending` and becomes visible
  only after moderation flips it to `approved`.

## Migrations

- Hand-written migrations compose the standard columns from
  `shared/migrations.py` (`pk_column`, `timestamp_columns`,
  `soft_delete_column`, `ugc_column`).
- Every migration carries a filled `-- THREAT/NOTES:` block and must
  downgrade; CI runs upgrade → downgrade base → upgrade.
