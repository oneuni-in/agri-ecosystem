"""In-memory Razorpay stand-in for service/router/worker/reconcile tests.
Mirrors modules.billing.razorpay_client.RazorpayClient's method surface
(subscriptions + M5 Task 9's ad-order Payment Links); tests mutate .subs/
.payment_links to inject remote state (e.g. reconciliation mismatches)."""

from typing import Any


class FakeRazorpay:
    def __init__(self) -> None:
        self.subs: dict[str, dict[str, Any]] = {}
        self.invoices: dict[str, dict[str, Any]] = {}
        self.payment_links: dict[str, dict[str, Any]] = {}
        self.payments: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, str]] = []
        # M5 Task 9: when set, create_payment_link raises RazorpayError
        # instead of returning - tests use this to exercise the "Razorpay
        # down, nothing persisted" 503 path.
        self.fail_create_payment_link = False
        # money-path review: when set, create_payment_link returns a 2xx
        # body missing id/short_url - tests use this to exercise the
        # "malformed response, still 503, never a KeyError" path.
        self.return_malformed_payment_link = False

    async def create_subscription(
        self, *, plan_id: str, total_count: int = 120, notes: dict[str, str] | None = None
    ) -> dict[str, Any]:
        sub_id = f"sub_{len(self.subs) + 1:06d}"
        record = {
            "id": sub_id,
            "status": "created",
            "plan_id": plan_id,
            "short_url": f"https://rzp.io/i/{sub_id}",
            "current_end": None,
        }
        self.subs[sub_id] = record
        self.calls.append(("create", sub_id))
        return record

    async def fetch_subscription(self, sub_id: str) -> dict[str, Any]:
        self.calls.append(("fetch", sub_id))
        return self.subs[sub_id]

    async def cancel_subscription(self, sub_id: str) -> dict[str, Any]:
        self.calls.append(("cancel", sub_id))
        self.subs[sub_id]["status"] = "cancelled"
        return self.subs[sub_id]

    async def fetch_invoice(self, invoice_id: str) -> dict[str, Any]:
        self.calls.append(("fetch_invoice", invoice_id))
        return self.invoices[invoice_id]

    # -- M5 Task 9: ad-order checkout ------------------------------------

    async def create_payment_link(
        self,
        *,
        amount_paise: int,
        description: str,
        reference_id: str,
        callback_url: str,
        expire_by: int,
        notes: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("create_payment_link", reference_id))
        if self.fail_create_payment_link:
            from modules.billing.razorpay_client import RazorpayError

            raise RazorpayError("fake: razorpay unreachable")
        if self.return_malformed_payment_link:
            return {"status": "created"}  # missing id/short_url
        plink_id = f"plink_{len(self.payment_links) + 1:06d}"
        record = {
            "id": plink_id,
            "short_url": f"https://rzp.io/l/{plink_id}",
            "status": "created",
            "amount": amount_paise,
            "description": description,
            "reference_id": reference_id,
            "callback_url": callback_url,
            "expire_by": expire_by,
            "notes": notes or {},
        }
        self.payment_links[plink_id] = record
        return record

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        self.calls.append(("fetch_payment", payment_id))
        return self.payments[payment_id]

    async def fetch_payment_link(self, plink_id: str) -> dict[str, Any]:
        self.calls.append(("fetch_payment_link", plink_id))
        return self.payment_links[plink_id]
