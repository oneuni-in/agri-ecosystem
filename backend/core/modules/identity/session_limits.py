"""Every session/refresh limit lives here (D09) - numbers the test suite pins.

Same contract as otp_limits.py: product security decisions, not deployment
knobs; change a value and its boundary test must change in the same commit.
"""

# 30-day rolling credential lifetime (spec assumption, confirmed in the PR
# description). Both sides match on purpose: the web session and the refresh
# family are two faces of "a device stays signed in for a month of disuse".
WEB_SESSION_TTL_SECONDS = 30 * 86400
REFRESH_TOKEN_TTL_SECONDS = 30 * 86400

# httpOnly + Secure + SameSite=Lax, host-only (no Domain attribute) - the
# session must never be readable by JS or sent to sibling subdomains.
SESSION_COOKIE_NAME = "agri_sid"

DEVICE_LABEL_MAX_CHARS = 64
