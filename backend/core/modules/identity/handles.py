"""Pure @handle rules (D06.B): lowercase a-z 0-9 underscore, 4-20 chars,
reserved-word blocklist from reserved_handles.txt, one free change ever.

No DB access here - handle uniqueness is the users.agri_id unique constraint,
and the change-once rule is the users.agri_id_changed_once flag; this module
is the single source of truth for what a handle may look like.
"""

import re
from pathlib import Path

HANDLE_RE = re.compile(r"^[a-z0-9_]{4,20}$")
_RESERVED_FILE = Path(__file__).with_name("reserved_handles.txt")


class HandleError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def load_reserved_handles(path: Path = _RESERVED_FILE) -> frozenset[str]:
    words = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        word = line.strip().lower()
        if word and not word.startswith("#"):
            words.add(word)
    return frozenset(words)


RESERVED_HANDLES = load_reserved_handles()


def normalize_handle(raw: str) -> str:
    return raw.strip().removeprefix("@").lower()


def validate_handle(raw: str) -> str:
    """Return the normalized handle, or raise HandleError.

    The blocklist runs before the format check so reserved words always
    report code="reserved", even the ones (api, www) that are also too short.
    """
    handle = normalize_handle(raw)
    if handle in RESERVED_HANDLES:
        raise HandleError("reserved", "this handle is reserved")
    if not HANDLE_RE.fullmatch(handle):
        raise HandleError("invalid_format", "handles are 4-20 chars of a-z, 0-9 and _")
    return handle


def can_change_handle(agri_id_changed_once: bool) -> bool:
    """One free change ever; the flag flips on the first change (D06.B)."""
    return not agri_id_changed_once
