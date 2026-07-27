"""Web-push endpoint allowlist (D28, SSRF defence).

A push subscription's `endpoint` is a URL the SERVER later POSTs to, and it
arrives from the browser under user control. Without an allowlist any
authenticated user could register an internal address (cloud metadata,
127.0.0.1, a private service) and turn the notify worker into an SSRF
proxy. Only the real push services are accepted - on write (router) AND
before every send (service), so rows stored before this gate cannot be
exploited either.
"""

from urllib.parse import urlparse

ALLOWED_PUSH_HOSTS = frozenset(
    {
        "fcm.googleapis.com",  # Chrome / Chromium
        "android.googleapis.com",  # legacy GCM host, still emitted by old Chrome
        "updates.push.services.mozilla.com",  # Firefox
    }
)

ALLOWED_PUSH_SUFFIXES = (
    ".notify.windows.com",  # Edge / WNS
    ".push.apple.com",  # Safari (web.push.apple.com)
    ".push.services.mozilla.com",  # Firefox autopush shards
)


def is_allowed_push_endpoint(url: str) -> bool:
    """True only for https URLs on a known push-service host."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not host:
        return False
    return host in ALLOWED_PUSH_HOSTS or host.endswith(ALLOWED_PUSH_SUFFIXES)
