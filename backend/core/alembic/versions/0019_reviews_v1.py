# backend/core/alembic/versions/0019_reviews_v1.py
"""reviews v1: polymorphic reviews + rating aggregates + review_approved coin rule.

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-19

"""
# -- THREAT/NOTES:
# - downgrade drops reviews + rating_aggregates (review content loss) and
#   deletes the review_approved coins rule + notify templates; ledger entries
#   already awarded are NOT clawed back (immutable ledger by trigger).
# - review_approved seeds weekly_cap=5 - first rule to exercise the
#   check_numeric_caps weekly window (D18 non-negotiable 2).
# - no table rewrites; enum + create_table only, safe online.

from collections.abc import Sequence

import sqlalchemy as sa
import uuid6
from sqlalchemy.dialects import postgresql

from alembic import op
from shared.migrations import pk_column, timestamp_columns, ugc_column

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_uuid = postgresql.UUID(as_uuid=True)

target_enum = postgresql.ENUM(
    "business", "product", "vendor", name="review_target_type", schema="directory"
)

channel_enum = postgresql.ENUM(
    "in_app", "sms", "email", name="notify_channel", schema="notify", create_type=False
)
locale_enum = postgresql.ENUM(
    "en", "ta", "hi", name="notify_locale", schema="notify", create_type=False
)

templates_table = sa.table(
    "templates",
    sa.column("id", _uuid),
    sa.column("key", sa.Text),
    sa.column("channel", channel_enum),
    sa.column("locale", locale_enum),
    sa.column("subject", sa.Text),
    sa.column("body", sa.Text),
    schema="notify",
)

rules_table = sa.table(
    "rules",
    sa.column("code", sa.Text),
    sa.column("amount", sa.BigInteger),
    sa.column("daily_cap", sa.Integer),
    sa.column("weekly_cap", sa.Integer),
    sa.column("total_cap", sa.Integer),
    schema="coins",
)

# every key ships en+ta+hi (CI gate); template has no {var} placeholders
SEED_TEMPLATES: list[tuple[str, str, str]] = [
    ("review_approved", "en", "Your review is approved and now visible."),
    ("review_approved", "ta", "உங்கள் மதிப்புரை அங்கீகரிக்கப்பட்டு இப்போது காட்டப்படுகிறது."),
    ("review_approved", "hi", "आपकी समीक्षा स्वीकृत हो गई है और अब दिखाई दे रही है."),
]


def upgrade() -> None:
    bind = op.get_bind()
    target_enum.create(bind, checkfirst=True)
    target_col = postgresql.ENUM(name="review_target_type", schema="directory", create_type=False)

    op.create_table(
        "reviews",
        pk_column(),
        sa.Column("author_user_id", _uuid, nullable=False),
        sa.Column("target_type", target_col, nullable=False),
        sa.Column("target_id", _uuid, nullable=False),
        sa.Column("rating", sa.SmallInteger, nullable=False),
        sa.Column("body", postgresql.JSONB, nullable=True),
        ugc_column(),
        *timestamp_columns(),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="rating_1_5"),
        sa.UniqueConstraint(
            "author_user_id",
            "target_type",
            "target_id",
            name="uq_directory_reviews_one_per_target",
        ),
        schema="directory",
    )
    op.create_index(
        "ix_directory_reviews_author_user_id", "reviews", ["author_user_id"], schema="directory"
    )
    op.create_index(
        "ix_directory_reviews_target_status_id",
        "reviews",
        ["target_type", "target_id", "moderation_status", "id"],
        schema="directory",
    )
    op.create_index(
        "ix_directory_reviews_moderation_status_id",
        "reviews",
        ["moderation_status", "id"],
        schema="directory",
    )

    op.create_table(
        "rating_aggregates",
        pk_column(),
        sa.Column("target_type", target_col, nullable=False),
        sa.Column("target_id", _uuid, nullable=False),
        sa.Column("rating_avg", sa.Numeric(3, 2), nullable=False),
        sa.Column("rating_count", sa.Integer, nullable=False),
        *timestamp_columns(),
        sa.UniqueConstraint(
            "target_type", "target_id", name="uq_directory_rating_aggregates_target"
        ),
        schema="directory",
    )

    # 0013's ALTER DEFAULT PRIVILEGES already covers new directory tables;
    # explicit per-table grant keeps the app_rt profile reviewable WITHOUT
    # re-granting UPDATE/DELETE on 0018's append-only spec_schemas.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON directory.reviews TO app_rt")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON directory.rating_aggregates TO app_rt")

    op.bulk_insert(
        rules_table,
        [
            {
                "code": "review_approved",
                "amount": 20,
                "daily_cap": None,
                "weekly_cap": 5,
                "total_cap": None,
            }
        ],
    )
    op.bulk_insert(
        templates_table,
        [
            {
                "id": uuid6.uuid7(),
                "key": key,
                "channel": "in_app",
                "locale": locale,
                "subject": None,
                "body": body,
            }
            for (key, locale, body) in SEED_TEMPLATES
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DELETE FROM notify.templates WHERE key = 'review_approved'")
    op.execute("DELETE FROM coins.rules WHERE code = 'review_approved'")
    op.drop_table("rating_aggregates", schema="directory")
    op.drop_table("reviews", schema="directory")
    sa.Enum(name="review_target_type", schema="directory").drop(bind, checkfirst=True)
