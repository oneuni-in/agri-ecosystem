"""Server-side image processing (D16, reused by D17 product images - the ONE
media helper, Sprint-2 rule A5: never fork a per-module variant).

Re-encoding to a fresh JPEG drops every metadata block (EXIF, GPS, XMP, ICC
beyond what Pillow re-embeds) by construction - there is no strip step to
forget. Uploads therefore MUST flow through here before shared.storage;
presigned direct-to-bucket uploads would bypass this and are deliberately
not offered.
"""

from io import BytesIO

from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000  # ~40MP; decompression-bomb guard
_ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

# Pillow raises DecompressionBombError beyond 2x this during open()
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class MediaError(ValueError):
    """Rejected upload; .code is the API error detail."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def reencode_image(data: bytes) -> tuple[bytes, str]:
    """bytes in -> (fresh JPEG bytes, "image/jpeg"), metadata-free."""
    if not data:
        raise MediaError("empty_file")
    if len(data) > MAX_IMAGE_BYTES:
        raise MediaError("too_large")
    try:
        img = Image.open(BytesIO(data))
        source_format = img.format
        img.load()
    except Image.DecompressionBombError as exc:
        raise MediaError("too_large") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise MediaError("unsupported_type") from exc
    if source_format not in _ALLOWED_FORMATS:
        raise MediaError("unsupported_type")
    if img.width * img.height > MAX_IMAGE_PIXELS:
        raise MediaError("too_large")
    out = BytesIO()
    img.convert("RGB").save(out, format="JPEG", quality=85)
    return out.getvalue(), "image/jpeg"
