"""reason_code -> i18n label key. UI localizes the key; the server never sends
localized copy. Keys resolve in each app's coins namespace."""

REASON_LABEL_KEYS: dict[str, str] = {
    "signup_complete": "coins.reason.signup_complete",
    "profile_100": "coins.reason.profile_100",
    "daily_visit": "coins.reason.daily_visit",
    "referral_referrer": "coins.reason.referral_referrer",
    "referral_referee": "coins.reason.referral_referee",
    "redeem": "coins.reason.redeem",
    "manual_adjust": "coins.reason.manual_adjust",
    "compensation": "coins.reason.compensation",
    "review_approved": "coins.reason.review_approved",
}


def label_key(reason_code: str) -> str:
    return REASON_LABEL_KEYS.get(reason_code, "coins.reason.unknown")
