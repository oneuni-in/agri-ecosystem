"""Strip payment-instrument and contact fields from webhook payloads BEFORE
they are persisted to billing.payment_events. "Never store card data"
applies to the raw log too; the D05 telemetry scrubber is the last line of
defence, not a licence. Drop-list, applied recursively."""

from typing import Any

DROP_KEYS = frozenset(
    {"card", "card_id", "vpa", "contact", "email", "token", "token_id", "bank_account"}
)


def scrub_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: scrub_payload(item) for key, item in value.items() if key not in DROP_KEYS}
    if isinstance(value, list):
        return [scrub_payload(item) for item in value]
    return value
