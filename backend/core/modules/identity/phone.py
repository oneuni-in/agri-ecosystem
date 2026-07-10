"""Pure E.164 phone normalization (D06 confirmed assumption: +91 default).

Bare 10-digit Indian mobile numbers (first digit 6-9) get the +91 prefix;
anything else must already be valid E.164. Error messages never include the
input value - phone numbers are PII and exceptions end up in logs.
"""

import re

E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
_INDIAN_MOBILE_RE = re.compile(r"^[6-9]\d{9}$")
_SEPARATORS_RE = re.compile(r"[\s\-()]")


class PhoneError(ValueError):
    """The input cannot be normalized to E.164."""


def normalize_phone(raw: str) -> str:
    cleaned = _SEPARATORS_RE.sub("", raw.strip())
    if _INDIAN_MOBILE_RE.fullmatch(cleaned):
        return f"+91{cleaned}"
    if E164_RE.fullmatch(cleaned):
        return cleaned
    raise PhoneError("phone number is not E.164 and not a bare Indian mobile number")
