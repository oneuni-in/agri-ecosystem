"""D30.B: the signup gate.

Two layers on purpose.

The flag is the control we lift when DLT approval lands - one row, no deploy,
and it takes effect within FLAG_CACHE_TTL_SECONDS.

The prod-on-mock refusal is an invariant, and it is the layer that actually
protects anyone. A flag alone cannot stop someone enabling signup in production
while `sms_provider` is still "mock": the app would happily accept signups and
every OTP would go nowhere, so users would see "we sent you a code" and receive
nothing. The spec's "do NOT launch real signup on the mock driver" therefore has
to be structural rather than a matter of remembering the right order to flip
things in.

The guard keys on `app_env == "prod"` ONLY. Dev and CI run the mock driver by
design and the D29 e2e suites drive real OTP login through it.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from settings import get_settings
from shared.flags import flag_enabled

SIGNUP_FLAG = "signup_enabled"


async def signup_allowed(session: AsyncSession | None = None) -> bool:
    """True when a new OTP may be issued.

    Checked at /auth/otp/request, the shared entry point for both signup and
    login - gating only "signup" would leave the login path issuing codes the
    mock driver silently drops.
    """
    settings = get_settings()
    # Invariant first: deliberately not overridable by the flag.
    if settings.app_env == "prod" and settings.sms_provider == "mock":
        return False
    return await flag_enabled(SIGNUP_FLAG, session=session)
