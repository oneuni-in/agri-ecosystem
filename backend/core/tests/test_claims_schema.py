# backend/core/tests/test_claims_schema.py
"""D16 schema: claims/verifications tables, claimable businesses
(owner_user_id nullable), business_claim rule seed, notify template seeds,
app_rt grants on the new tables."""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.models import Template

EXPECTED_TEMPLATE_KEYS = {
    "claim_approved",
    "claim_rejected",
    "verification_approved",
    "verification_rejected",
}


async def _columns(session: AsyncSession, table: str) -> set[str]:
    rows = await session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'directory' AND table_name = :t"
        ),
        {"t": table},
    )
    return {r[0] for r in rows}


async def test_claims_table_shape(db_session: AsyncSession) -> None:
    cols = await _columns(db_session, "claims")
    assert {
        "id",
        "business_id",
        "claimant_user_id",
        "status",
        "evidence_docs",
        "decision_note",
        "decided_by",
        "decided_at",
        "created_at",
        "updated_at",
    } <= cols


async def test_verifications_table_shape(db_session: AsyncSession) -> None:
    cols = await _columns(db_session, "verifications")
    assert {
        "id",
        "business_id",
        "method",
        "doc_keys",
        "status",
        "notes",
        "decided_by",
        "decided_at",
    } <= cols


async def test_owner_user_id_is_nullable(db_session: AsyncSession) -> None:
    row = await db_session.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'directory' AND table_name = 'businesses' "
            "AND column_name = 'owner_user_id'"
        )
    )
    assert row.scalar_one() == "YES"


async def test_one_pending_claim_index_exists(db_session: AsyncSession) -> None:
    row = await db_session.execute(
        text(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = 'directory' "
            "AND indexname = 'uq_directory_claims_one_pending'"
        )
    )
    indexdef = row.scalar_one()
    assert "UNIQUE" in indexdef and "pending" in indexdef


async def test_business_claim_rule_seeded(db_session: AsyncSession) -> None:
    row = await db_session.execute(
        text("SELECT amount, active FROM coins.rules WHERE code = 'business_claim'")
    )
    amount, active = row.one()
    assert amount == 200 and active is True


async def test_claim_templates_seeded_all_locales(db_session: AsyncSession) -> None:
    rows = (
        await db_session.scalars(select(Template).where(Template.key.in_(EXPECTED_TEMPLATE_KEYS)))
    ).all()
    seen = {(r.key, r.channel, r.locale) for r in rows}
    expected = {(k, "in_app", loc) for k in EXPECTED_TEMPLATE_KEYS for loc in ("en", "ta", "hi")}
    assert seen == expected


async def test_app_rt_has_dml_on_claims(db_session: AsyncSession) -> None:
    rows = await db_session.execute(
        text(
            "SELECT privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = 'app_rt' AND table_schema = 'directory' "
            "AND table_name = 'claims'"
        )
    )
    assert {"SELECT", "INSERT", "UPDATE", "DELETE"} <= {r[0] for r in rows}
