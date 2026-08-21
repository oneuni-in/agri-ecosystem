"""Avatar upload validation (D11.A) - pure byte-sniffing, no I/O.

The client's Content-Type header is never consulted: type comes from magic
numbers only. JPEG/PNG/WebP allowlist; SVG is deliberately absent (it is a
script vector), GIF adds nothing for a profile photo. 2 MiB cap keeps the
media bucket boring until a real media pipeline lands.
"""

import uuid6

MAX_AVATAR_BYTES = 2 * 1024 * 1024

_SIGNATURES: tuple[tuple[bytes, str, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
)


# ext -> content type, DERIVED from the signature table above so a new
# accepted format cannot be servable without also being sniffable. Used when
# serving the stored object back (ID-U1 P7): the bucket keeps bytes, not the
# content type it was uploaded with.
AVATAR_CONTENT_TYPES: dict[str, str] = {
    **{ext: content_type for _magic, content_type, ext in _SIGNATURES},
    "webp": "image/webp",
}


class AvatarError(ValueError):
    """Rejected upload; .code is the API error detail."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def sniff_image(data: bytes) -> tuple[str, str] | None:
    for magic, content_type, ext in _SIGNATURES:
        if data.startswith(magic):
            return content_type, ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def validate_avatar(data: bytes) -> tuple[str, str]:
    if not data:
        raise AvatarError("empty_file")
    if len(data) > MAX_AVATAR_BYTES:
        raise AvatarError("too_large")
    sniffed = sniff_image(data)
    if sniffed is None:
        raise AvatarError("unsupported_type")
    return sniffed


def avatar_object_key(ext: str) -> str:
    """Random UUIDv7 key: never derived from user identity (bucket paths must
    not leak who owns which object)."""
    return f"avatars/{uuid6.uuid7().hex}.{ext}"
