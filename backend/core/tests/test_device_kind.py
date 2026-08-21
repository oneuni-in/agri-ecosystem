"""ID-U1 P8: the coarse device description shown on /devices.

Pure function, so these are the cheap tests that matter - the ordering traps
(Chrome's UA says Safari, Edge's says Chrome, Android's says Linux) are
exactly what a naive scan gets wrong.
"""

from modules.identity.device_kind import MAX_DEVICE_KIND_CHARS, describe_device

ANDROID_CHROME = (
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Mobile Safari/537.36"
)
WINDOWS_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
WINDOWS_EDGE = WINDOWS_CHROME + " Edg/120.0.0.0"
IPHONE_SAFARI = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
MAC_FIREFOX = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0"


def test_android_chrome_is_not_reported_as_linux_safari() -> None:
    # the two traps together: Android UAs contain "Linux", and every Chrome UA
    # contains "Safari".
    assert describe_device(ANDROID_CHROME) == "Android - Chrome"


def test_edge_is_not_reported_as_chrome() -> None:
    assert describe_device(WINDOWS_EDGE) == "Windows - Edge"


def test_windows_chrome() -> None:
    assert describe_device(WINDOWS_CHROME) == "Windows - Chrome"


def test_iphone_safari_is_not_reported_as_mac() -> None:
    # iPhone UAs say "like Mac OS X"; the iPhone pattern has to win.
    assert describe_device(IPHONE_SAFARI) == "iPhone - Safari"


def test_mac_firefox() -> None:
    assert describe_device(MAC_FIREFOX) == "Mac - Firefox"


def test_installed_app_beats_the_browser_underneath_it() -> None:
    assert describe_device(ANDROID_CHROME, "standalone") == "Installed app"


def test_unknown_is_none_rather_than_a_guess() -> None:
    # A wrong-but-plausible label is worse than no label: the screen says
    # "Unknown device" and the farmer trusts the rest of the row.
    assert describe_device("curl/8.4.0") is None
    assert describe_device(None) is None
    assert describe_device("") is None


def test_partial_match_still_says_something_useful() -> None:
    assert describe_device("Mozilla/5.0 (Windows NT 10.0)") == "Windows"


def test_never_exceeds_the_column_budget() -> None:
    absurd = "Mozilla/5.0 (Windows NT 10.0) " + "x" * 500 + " Chrome/1.0"
    described = describe_device(absurd)
    assert described is not None and len(described) <= MAX_DEVICE_KIND_CHARS
