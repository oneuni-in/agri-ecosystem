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
    # business_claim has been awarded by the worker since D16 but was never
    # mapped here, so a user who claimed a business saw "unknown" against
    # the largest single award on their ledger. A-U4 W2 fixes it.
    "business_claim": "coins.reason.business_claim",
    "daily_visit_streak": "coins.reason.daily_visit_streak",
}


def label_key(reason_code: str) -> str:
    return REASON_LABEL_KEYS.get(reason_code, "coins.reason.unknown")
