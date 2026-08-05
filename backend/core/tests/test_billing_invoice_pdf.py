"""M5 Task 12: GST invoice PDF rendering (pure), the worker sweep that
renders + stores + queues the email, and the advertiser's own download
route. `render_invoice_pdf` is pure (no I/O, no settings) - its own tests
never touch the DB. The sweep and download-route tests register local
lookups stubs (test_ads_moderation_source.py precedent) so business/contact
resolution is deterministic regardless of what earlier test modules left
registered on shared.lookups's process-global resolvers."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from main import create_app
from modules.ads.models import Campaign
from modules.billing.ad_orders import run_invoice_pdf_sweep
from modules.billing.invoice_pdf import render_invoice_pdf
from modules.billing.models import AdOrder, Invoice
from settings import get_settings
from shared import storage
from shared.db import get_session
from shared.flags import FeatureFlag, reset_flag_cache
from shared.lookups import (
    BusinessRef,
    NotifyContact,
    register_business_resolver,
    register_contact_resolver,
)
from shared.security import register_principal_resolver

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)

OWNER = uuid.uuid4()
STRANGER = uuid.uuid4()
BUSINESS_ID = uuid.uuid4()


def _biz_resolver(name: str = "Kovai Mills") -> Any:
    async def _resolve(session: AsyncSession, business_id: uuid.UUID) -> BusinessRef | None:
        if business_id == BUSINESS_ID:
            return BusinessRef(id=business_id, owner_user_id=OWNER, name=name)
        return None

    return _resolve


async def _contact_resolver_ok(session: AsyncSession, user_id: uuid.UUID) -> NotifyContact | None:
    return NotifyContact(email="owner@example.com", locale="ta")


async def _contact_resolver_none(session: AsyncSession, user_id: uuid.UUID) -> NotifyContact | None:
    return None


# ---------------------------------------------------------------------------
# render_invoice_pdf - pure function, no DB/app needed


def _kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "invoice_number": "MILK-26-27-000001",
        "issued_on": date(2026, 8, 5),
        "seller": ("Oneuni Technologies", "33AAAAA0000A1Z5", "Coimbatore, TN"),
        "buyer_name": "Kovai Mills",
        "buyer_gstin": "33BBBBB1111B1Z5",
        "lines": [("5,000 ad views @ CPM T2", 100_000)],
        "taxable_paise": 100_000,
        "gst_paise": 18_000,
        "total_paise": 118_000,
    }
    base.update(overrides)
    return base


def test_pdf_bytes_start_with_pdf_magic() -> None:
    pdf_bytes = render_invoice_pdf(**_kwargs())
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 200


def test_sac_line_present() -> None:
    pdf_bytes = render_invoice_pdf(**_kwargs())
    assert b"SAC 998365" in pdf_bytes


def test_same_state_gstin_splits_cgst_sgst() -> None:
    pdf_bytes = render_invoice_pdf(**_kwargs(buyer_gstin="33BBBBB1111B1Z5"))
    assert b"CGST" in pdf_bytes
    assert b"SGST" in pdf_bytes
    assert b"IGST" not in pdf_bytes


def test_different_state_gstin_uses_igst() -> None:
    pdf_bytes = render_invoice_pdf(**_kwargs(buyer_gstin="29BBBBB1111B1Z5"))
    assert b"IGST" in pdf_bytes
    assert b"CGST" not in pdf_bytes
    assert b"SGST" not in pdf_bytes


def test_missing_buyer_gstin_defaults_to_cgst_sgst_split() -> None:
    """v1 simplification pinned: no GSTIN = unregistered B2C = assumed
    same-state, never IGST (see invoice_pdf.py's module docstring)."""
    pdf_bytes = render_invoice_pdf(**_kwargs(buyer_gstin=None))
    assert b"CGST" in pdf_bytes
    assert b"SGST" in pdf_bytes
    assert b"IGST" not in pdf_bytes


def test_cgst_sgst_split_sums_to_gst_total_even_when_odd() -> None:
    # gst_paise=18_001 is deliberately odd (1 extra paisa) - cgst+sgst must
    # still equal it exactly (90.00 + 90.01 = 180.01), not silently drop or
    # duplicate the odd paisa.
    pdf_bytes = render_invoice_pdf(
        **_kwargs(buyer_gstin=None, gst_paise=18_001, total_paise=118_001)
    )
    assert b"Rs. 90.00" in pdf_bytes
    assert b"Rs. 90.01" in pdf_bytes


# ---------------------------------------------------------------------------
# run_invoice_pdf_sweep


async def _seed_campaign(session: AsyncSession) -> Campaign:
    """Only the HTTP list_orders tests need this - GET /billing/ad-orders
    resolves campaign_id -> business_id via shared.lookups.
    resolve_campaign_billing (main.create_app wires the real ads resolver),
    so a bare random campaign_id 404s there even though the sweep tests
    (which never touch that route) don't need a real row at all."""
    campaign = Campaign(
        advertiser_business_id=BUSINESS_ID,
        name="Kharif push",
        status="active",
        flight_start=date(2026, 8, 1),
        flight_end=date(2026, 9, 1),
        price_paise=118_000,
        price_subtotal_paise=100_000,
        price_gst_paise=18_000,
        pricing_model="cpm",
        rate_card_version=1,
        budget_serves_total=5000,
    )
    session.add(campaign)
    await session.flush()
    return campaign


async def _seed_paid_order_with_invoice(
    session: AsyncSession,
    *,
    campaign_id: uuid.UUID | None = None,
    quote: dict[str, Any] | None = None,
    buyer_gstin: str | None = None,
    invoice_number: str = "MILK-26-27-000001",
    taxable_paise: int = 100_000,
    gst_paise: int = 18_000,
    total_paise: int = 118_000,
) -> tuple[AdOrder, Invoice]:
    order = AdOrder(
        campaign_id=campaign_id or uuid.uuid4(),
        business_id=BUSINESS_ID,
        status="paid",
        subtotal_paise=taxable_paise,
        gst_paise=gst_paise,
        total_paise=total_paise,
        quote=quote if quote is not None else {"campaign_name": "Kharif push"},
        buyer_gstin=buyer_gstin,
        razorpay_plink_id=f"plink_{uuid.uuid4().hex[:8]}",
        razorpay_payment_id=f"pay_{uuid.uuid4().hex[:8]}",
    )
    session.add(order)
    await session.flush()
    invoice = Invoice(
        order_id=order.id,
        subscription_id=None,
        amount_paise=total_paise,
        taxable_paise=taxable_paise,
        gst_paise=gst_paise,
        status="paid",
        invoice_number=invoice_number,
    )
    session.add(invoice)
    await session.flush()
    return order, invoice


async def test_sweep_renders_stores_and_queues_email_event(
    db_session: AsyncSession, object_store: dict[str, bytes]
) -> None:
    register_business_resolver(_biz_resolver())
    register_contact_resolver(_contact_resolver_ok)
    _, invoice = await _seed_paid_order_with_invoice(
        db_session,
        quote={"campaign_name": "Kharif push", "lines": [["5,000 ad views @ CPM T2", 100_000]]},
    )

    processed, pending = await run_invoice_pdf_sweep(db_session, now=NOW)

    assert processed == 1
    await db_session.refresh(invoice)
    expected_key = f"invoices/{invoice.id.hex}.pdf"
    assert invoice.pdf_key == expected_key
    assert expected_key in object_store
    assert object_store[expected_key].startswith(b"%PDF")

    assert len(pending) == 1
    event_type, payload = pending[0]
    assert event_type == "billing.ad_invoice"
    assert payload["user_id"] == str(OWNER)
    assert payload["locale"] == "ta"
    assert payload["email"] == "owner@example.com"
    assert payload["attachment_key"] == expected_key
    assert payload["attachment_filename"] == f"{invoice.invoice_number}.pdf"
    assert payload["vars"]["invoice_number"] == invoice.invoice_number
    assert payload["vars"]["business_name"] == "Kovai Mills"
    assert payload["vars"]["total"] == "1,180.00"


async def test_sweep_falls_back_to_single_line_when_quote_has_no_lines(
    db_session: AsyncSession, object_store: dict[str, bytes]
) -> None:
    register_business_resolver(_biz_resolver())
    register_contact_resolver(_contact_resolver_ok)
    _, invoice = await _seed_paid_order_with_invoice(db_session, quote={"campaign_name": "X"})

    processed, _pending = await run_invoice_pdf_sweep(db_session, now=NOW)

    assert processed == 1
    await db_session.refresh(invoice)
    assert invoice.pdf_key is not None
    assert b"Advertising services" in object_store[invoice.pdf_key]


async def test_sweep_sets_pdf_key_but_skips_event_when_contact_unresolvable(
    db_session: AsyncSession, object_store: dict[str, bytes]
) -> None:
    register_business_resolver(_biz_resolver())
    register_contact_resolver(_contact_resolver_none)
    _, invoice = await _seed_paid_order_with_invoice(db_session)

    processed, pending = await run_invoice_pdf_sweep(db_session, now=NOW)

    assert processed == 1
    assert pending == []
    await db_session.refresh(invoice)
    assert invoice.pdf_key is not None
    assert invoice.pdf_key in object_store


async def test_sweep_storage_error_skips_row_for_retry(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    register_business_resolver(_biz_resolver())
    register_contact_resolver(_contact_resolver_ok)
    _, invoice = await _seed_paid_order_with_invoice(db_session)

    async def _boom(key: str, data: bytes, content_type: str) -> None:
        raise storage.StorageError("object storage write failed")

    monkeypatch.setattr(storage, "put_object", _boom)

    processed, pending = await run_invoice_pdf_sweep(db_session, now=NOW)

    assert processed == 0
    assert pending == []
    await db_session.refresh(invoice)
    assert invoice.pdf_key is None  # untouched - next tick retries


async def test_sweep_ignores_invoices_already_carrying_a_pdf_key(
    db_session: AsyncSession, object_store: dict[str, bytes]
) -> None:
    register_business_resolver(_biz_resolver())
    register_contact_resolver(_contact_resolver_ok)
    _, invoice = await _seed_paid_order_with_invoice(db_session)
    invoice.pdf_key = "invoices/already-done.pdf"
    await db_session.flush()

    processed, pending = await run_invoice_pdf_sweep(db_session, now=NOW)

    assert processed == 0
    assert pending == []
    assert object_store == {}


# ---------------------------------------------------------------------------
# HTTP: AdOrderOut invoice exposure (Task 12 review carry-forward 1) +
# GET /billing/ad-invoices/{id}/pdf (carry-forward 2)


class _Principal:
    def __init__(self, user_id: uuid.UUID) -> None:
        self.user_id = user_id
        self.roles = ("user",)


def _as(user_id: uuid.UUID) -> dict[str, str]:
    return {"x-test-user": str(user_id)}


@pytest.fixture
async def api(
    db_session: AsyncSession, object_store: dict[str, bytes]
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    get_settings.cache_clear()
    app = create_app()
    register_business_resolver(_biz_resolver())
    register_contact_resolver(_contact_resolver_ok)

    async def _resolver(request: Request, session: AsyncSession) -> _Principal | None:
        header = request.headers.get("x-test-user")
        if header is None:
            return None
        return _Principal(uuid.UUID(header))

    register_principal_resolver(_resolver)

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session_override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db_session


async def _enable_billing(session: AsyncSession) -> None:
    flag = await session.get(FeatureFlag, "billing_enabled")
    assert flag is not None
    flag.enabled = True
    await session.flush()
    reset_flag_cache()


async def test_list_orders_exposes_invoice_number_and_has_pdf(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_billing(session)
    campaign = await _seed_campaign(session)
    order, invoice = await _seed_paid_order_with_invoice(session, campaign_id=campaign.id)
    invoice.pdf_key = f"invoices/{invoice.id.hex}.pdf"
    await session.flush()

    response = await client.get(
        f"/billing/ad-orders?campaign_id={order.campaign_id}", headers=_as(OWNER)
    )
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["invoice_id"] == str(invoice.id)
    assert item["invoice_number"] == invoice.invoice_number
    assert item["has_pdf"] is True


async def test_list_orders_unpaid_order_has_no_invoice_fields(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_billing(session)
    campaign = await _seed_campaign(session)
    order = AdOrder(
        campaign_id=campaign.id,
        business_id=BUSINESS_ID,
        status="created",
        subtotal_paise=100_000,
        gst_paise=18_000,
        total_paise=118_000,
        quote={"campaign_name": "Kharif push"},
        razorpay_plink_id=f"plink_{uuid.uuid4().hex[:8]}",
        razorpay_short_url="https://rzp.io/l/plink_x",
    )
    session.add(order)
    await session.flush()

    response = await client.get(
        f"/billing/ad-orders?campaign_id={order.campaign_id}", headers=_as(OWNER)
    )
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["invoice_id"] is None
    assert item["invoice_number"] is None
    assert item["has_pdf"] is False


async def test_download_pdf_owner_gets_stored_bytes(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_billing(session)
    _, invoice = await _seed_paid_order_with_invoice(session)
    key = f"invoices/{invoice.id.hex}.pdf"
    stored = b"%PDF-1.3 stored bytes"
    await storage.put_object(key, stored, "application/pdf")
    invoice.pdf_key = key
    await session.flush()

    response = await client.get(f"/billing/ad-invoices/{invoice.id}/pdf", headers=_as(OWNER))
    assert response.status_code == 200
    assert response.content == stored
    assert response.headers["content-type"] == "application/pdf"
    assert invoice.invoice_number is not None
    assert invoice.invoice_number in response.headers["content-disposition"]


async def test_download_pdf_regenerates_on_the_fly_when_pdf_key_missing(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    """Read-only: the download route renders a fresh PDF but must NOT write
    pdf_key back - only the worker sweep is allowed to do that."""
    client, session = api
    await _enable_billing(session)
    _, invoice = await _seed_paid_order_with_invoice(session)
    assert invoice.pdf_key is None

    response = await client.get(f"/billing/ad-invoices/{invoice.id}/pdf", headers=_as(OWNER))
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")

    await session.refresh(invoice)
    assert invoice.pdf_key is None  # still not persisted by the GET


async def test_download_pdf_foreign_user_gets_404(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_billing(session)
    _, invoice = await _seed_paid_order_with_invoice(session)

    response = await client.get(f"/billing/ad-invoices/{invoice.id}/pdf", headers=_as(STRANGER))
    assert response.status_code == 404


async def test_download_pdf_unknown_invoice_404(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_billing(session)
    response = await client.get(f"/billing/ad-invoices/{uuid.uuid4()}/pdf", headers=_as(OWNER))
    assert response.status_code == 404


async def test_download_pdf_storage_miss_is_404(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    await _enable_billing(session)
    _, invoice = await _seed_paid_order_with_invoice(session)
    invoice.pdf_key = "invoices/does-not-exist.pdf"  # pdf_key set, object never written
    await session.flush()

    response = await client.get(f"/billing/ad-invoices/{invoice.id}/pdf", headers=_as(OWNER))
    assert response.status_code == 404


async def test_download_pdf_flag_off_404s(
    api: tuple[httpx.AsyncClient, AsyncSession],
) -> None:
    client, session = api
    _, invoice = await _seed_paid_order_with_invoice(session)
    response = await client.get(f"/billing/ad-invoices/{invoice.id}/pdf", headers=_as(OWNER))
    assert response.status_code == 404
