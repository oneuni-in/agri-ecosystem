"""In-memory Razorpay stand-in for service/router/worker/reconcile tests.
Mirrors modules.billing.razorpay_client.RazorpayClient's four methods; tests
mutate .subs to inject remote state (e.g. reconciliation mismatches)."""

from typing import Any


class FakeRazorpay:
    def __init__(self) -> None:
        self.subs: dict[str, dict[str, Any]] = {}
        self.invoices: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, str]] = []

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
