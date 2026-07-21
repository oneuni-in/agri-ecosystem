"""Minimal async Razorpay REST client (D20). Deliberately NOT the official
SDK: it is sync-only, adds a dependency, and the money path must stay small
enough for line-by-line human review. Basic auth (key_id:key_secret); only
the four calls this module needs. Every method re-checks billing_enabled -
defense in depth beneath the route/worker gates - so a code path that
somehow reaches here while dark still cannot touch Razorpay. Never logs
request or response bodies."""

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


def get_client() -> RazorpayClient:
    settings = get_settings()
    return RazorpayClient(settings.razorpay_key_id, settings.razorpay_key_secret)
