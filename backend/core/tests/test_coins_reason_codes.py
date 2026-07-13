from modules.coins.reason_codes import REASON_LABEL_KEYS, label_key


def test_every_sprint1_reason_has_a_label() -> None:
    for code in [
        "signup_complete",
        "profile_100",
        "daily_visit",
        "referral_referrer",
        "referral_referee",
        "redeem",
        "manual_adjust",
        "compensation",
    ]:
        assert code in REASON_LABEL_KEYS


def test_unknown_reason_falls_back() -> None:
    assert label_key("nope") == "coins.reason.unknown"
