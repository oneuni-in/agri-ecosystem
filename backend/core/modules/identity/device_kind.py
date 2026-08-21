"""Coarse device descriptions for the /devices list (ID-U1 P8).

Pure: no I/O, no clock, no DB.

WHY A STORED STRING AND NOT THE USER AGENT. Sessions have never kept a raw
user agent - only `device_fingerprint`, a SHA-256 of UA + platform, which is
deliberately one-way and cannot answer "what device is this?". So the list
had nothing to show and printed the OAuth client id twice instead.

The fix could have been a `user_agent` column. It is not, on purpose: a full
UA string is a high-entropy fingerprint at rest, and this feature needs
exactly one sentence a person can recognise their own phone by. We derive
that sentence at session creation and store ONLY it, so the row keeps strictly
less about the visitor than the alternative while answering the question the
screen actually asks. `device_fingerprint` continues to do the security job.

The parsing is intentionally shallow. This is a recognition aid ("is that my
laptop or someone else's?"), not analytics, and a wrong-but-plausible label is
worse than a vague one - so anything unrecognised becomes None and renders as
"Unknown device" rather than a guess.
"""

import re

MAX_DEVICE_KIND_CHARS = 40

# Order matters: the first match wins, and the more specific pattern comes
# first. Chrome's UA contains "Safari", Edge's contains "Chrome", and every
# Android browser contains "Linux" - a naive scan gets all three wrong.
_OS_PATTERNS: tuple[tuple[str, str], ...] = (
    ("Android", "Android"),
    ("iPhone", "iPhone"),
    ("iPad", "iPad"),
    ("Windows", "Windows"),
    ("Mac OS X", "Mac"),
    ("Macintosh", "Mac"),
    ("CrOS", "ChromeOS"),
    ("Linux", "Linux"),
)

_BROWSER_PATTERNS: tuple[tuple[str, str], ...] = (
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("SamsungBrowser", "Samsung Internet"),
    ("Firefox/", "Firefox"),
    ("Chrome/", "Chrome"),
    ("Safari/", "Safari"),
)

# An installed PWA reports standalone display mode; browsers do not. Clients
# send it as a client hint on the session-creating request.
_PWA_HINT = re.compile(r"standalone|minimal-ui|fullscreen", re.IGNORECASE)


def describe_device(user_agent: str | None, platform: str | None = None) -> str | None:
    """ "Android - Chrome", "Installed app", or None when we cannot tell.

    None is a real answer and the honest one: the screen renders "Unknown
    device", which is better than confidently naming the wrong thing.
    """
    if not user_agent:
        return None
    if platform and _PWA_HINT.search(platform):
        return "Installed app"
    os_name = next((label for needle, label in _OS_PATTERNS if needle in user_agent), None)
    browser = next((label for needle, label in _BROWSER_PATTERNS if needle in user_agent), None)
    if os_name and browser:
        return f"{os_name} - {browser}"[:MAX_DEVICE_KIND_CHARS]
    return (os_name or browser or None) and (os_name or browser or "")[:MAX_DEVICE_KIND_CHARS]
