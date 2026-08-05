"""Minimal async Razorpay REST client (D20/M5). Deliberately NOT the
official SDK: it is sync-only, adds a dependency, and the money path must
stay small enough for line-by-line human review. Basic auth
(key_id:key_secret); only the calls this module needs. Every LIVE call
re-checks billing_enabled inside `_request` - defense in depth beneath the
route/worker gates - so a code path that somehow reaches here while dark
still cannot touch Razorpay. The three M5 checkout/reconcile methods
short-circuit to a canned response when `razorpay_test_stub` is set
(e2e-only, never in prod) BEFORE that gate, matching the brief's spec
verbatim - the stub exists precisely so e2e can run with billing_enabled
on but zero real Razorpay credentials. Never logs request or response
bodies."""

from typing import Any, cast

import httpx

from settings import get_settings
from shared.flags import flag_enabled

BASE_URL = "https://api.razorpay.com"
TIMEOUT_SECONDS = 15.0


class RazorpayError(RuntimeError):
    """Transport failure or non-2xx from Razorpay (body never included)."""


class BillingDisabledError(RuntimeError):
    """A live call was attempted while billing_enabled is off."""


class RazorpayClient:
    def __init__(
        self,
        key_id: str,
        key_secret: str,
        *,
        base_url: str = BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._key_id = key_id
        self._key_secret = key_secret
        self._base_url = base_url
        self._transport = transport

    async def _request(
        self, method: str, path: str, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not await flag_enabled("billing_enabled"):
            raise BillingDisabledError("billing_enabled is off - live Razorpay calls are barred")
        if not self._key_id or not self._key_secret:
            raise RazorpayError("razorpay credentials not configured")
        async with httpx.AsyncClient(
            base_url=self._base_url,
            auth=(self._key_id, self._key_secret),
            timeout=TIMEOUT_SECONDS,
            transport=self._transport,
        ) as client:
            try:
                response = await client.request(method, path, json=json_body)
            except httpx.HTTPError as exc:
                raise RazorpayError(f"razorpay {method} {path}: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise RazorpayError(f"razorpay {method} {path} -> {response.status_code}")
        try:
            return cast(dict[str, Any], response.json())
        except ValueError as exc:
            # 2xx but not JSON - never include the body (may carry secrets).
            raise RazorpayError(f"razorpay {method} {path}: invalid json") from exc

    async def create_subscription(
        self, *, plan_id: str, total_count: int = 120, notes: dict[str, str] | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "plan_id": plan_id,
            "total_count": total_count,
            "customer_notify": 1,
        }
        if notes:
            body["notes"] = notes
        return await self._request("POST", "/v1/subscriptions", body)

    async def fetch_subscription(self, sub_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/subscriptions/{sub_id}")

    async def cancel_subscription(self, sub_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/v1/subscriptions/{sub_id}/cancel")

    async def fetch_invoice(self, invoice_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/invoices/{invoice_id}")

    # -- M5 Task 9: ad-order checkout via hosted Payment Links -----------
    # razorpay_test_stub short-circuits BEFORE _request's billing_enabled
    # gate (and therefore before any network call) - e2e only, canned
    # responses, never live credentials. Never flip it on in prod.

    async def create_payment_link(
        self,
        *,
        amount_paise: int,
        description: str,
        reference_id: str,
        callback_url: str,
        notes: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if get_settings().razorpay_test_stub:
            return {
                "id": f"plink_test_{reference_id.replace('-', '')[:14]}",
                "short_url": callback_url,  # e2e: "checkout" bounces straight back
                "status": "created",
            }
        return await self._request(
            "POST",
            "/v1/payment_links",
            json_body={
                "amount": amount_paise,
                "currency": "INR",
                "description": description,
                "reference_id": reference_id,
                "callback_url": callback_url,
                "callback_method": "get",
                "notes": notes or {},
            },
        )

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        if get_settings().razorpay_test_stub:
            return {"id": payment_id, "status": "captured", "amount": 0}
        return await self._request("GET", f"/v1/payments/{payment_id}")

    async def fetch_payment_link(self, plink_id: str) -> dict[str, Any]:
        if get_settings().razorpay_test_stub:
            return {"id": plink_id, "status": "paid"}
        return await self._request("GET", f"/v1/payment_links/{plink_id}")


def get_client() -> RazorpayClient:
    settings = get_settings()
    return RazorpayClient(settings.razorpay_key_id, settings.razorpay_key_secret)
