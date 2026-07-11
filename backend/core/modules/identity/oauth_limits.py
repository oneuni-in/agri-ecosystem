"""OAuth2 lifetimes (D08) - the numbers the test suite proves.

Like otp_limits.py: change a value and its boundary test MUST change with it.
Nothing here is read from the environment on purpose: these are product
security decisions, not deployment knobs.
"""

# Authorization codes are one redirect round-trip long. A code either becomes
# a token within a minute or it never will.
AUTH_CODE_TTL_SECONDS = 60

# Access tokens are short-lived by design; refresh rotation (D09) carries the
# long-lived session, not this JWT.
ACCESS_TOKEN_TTL_SECONDS = 900  # 15 minutes
