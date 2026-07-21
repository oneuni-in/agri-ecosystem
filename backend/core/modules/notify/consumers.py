"""Event -> notification mapping (D12). Producers know nothing about notify;
they publish domain events with a self-contained payload (destination +
locale resolved at emit time, used once here, never logged)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from modules.notify.service import NotifyRequest, dispatch
from shared.events import Event
from shared.i18n import SUPPORTED_LOCALES
from shared.telemetry import get_logger

logger = get_logger(__name__)

STREAMS = ("identity", "notify", "directory", "billing")
CONSUMER_GROUP = "notify"

EVENT_ROUTES: dict[str, tuple[str, frozenset[str]]] = {
    "identity.signup_completed": ("welcome", frozenset({"email"})),
    "identity.login_new_device": ("login_new_device", frozenset({"sms", "email"})),
    "identity.role_changed": ("role_changed", frozenset()),
    "notify.announce": ("generic_announce", frozenset({"email"})),
    # D16 claim/verification decisions: in-app only - directory events carry
    # no destination (module independence), so extra channels stay empty.
    "business.claimed": ("claim_approved", frozenset()),
    "directory.claim_rejected": ("claim_rejected", frozenset()),
    "directory.verification_approved": ("verification_approved", frozenset()),
    "directory.verification_rejected": ("verification_rejected", frozenset()),
    # D18: in-app only, same rationale as the D16 claim/verification routes
    # above - directory events carry no destination.
    "review.approved": ("review_approved", frozenset()),
    "lead.created": ("lead_received", frozenset()),
    "lead.responded": ("lead_response", frozenset()),
    # D20 billing/dunning: money events DO carry a destination - billing
    # resolves the owner's verified email + locale at emit time through
    # shared.lookups (identity's registered adapter), so email rides along
    # with in-app. subscription_renewed is deliberately unrouted (silent).
    "billing.payment_failed": ("dunning_payment_failed", frozenset({"email"})),
    "billing.dunning_reminder": ("dunning_reminder", frozenset({"email"})),
    "billing.subscription_canceled": ("subscription_canceled", frozenset({"email"})),
    "billing.subscription_activated": ("subscription_activated", frozenset({"email"})),
}


async def handle_event(session: AsyncSession, event: Event) -> None:
    route = EVENT_ROUTES.get(event.type)
    if route is None:
        return  # not every identity-stream event is a notification (e.g. profile.completed)
    template_key, channels = route
    payload = event.payload
    locale = payload.get("locale") or "en"
    if locale not in SUPPORTED_LOCALES:
        locale = "en"
    request = NotifyRequest(
        user_id=uuid.UUID(str(payload["user_id"])),
        template_key=template_key,
        payload=dict(payload.get("vars") or {}),
        locale=locale,
        email=payload.get("email"),
        phone=payload.get("phone"),
        channels=channels,
    )
    await dispatch(session, request)
