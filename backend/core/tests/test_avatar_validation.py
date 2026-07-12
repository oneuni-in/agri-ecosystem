"""D11.A: avatar bytes are judged by magic numbers, never by client headers."""

import pytest

from modules.identity.avatar import (
    MAX_AVATAR_BYTES,
    AvatarError,
    avatar_object_key,
    validate_avatar,
)

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 32


@pytest.mark.parametrize(
    ("data", "content_type", "ext"),
    [(JPEG, "image/jpeg", "jpg"), (PNG, "image/png", "png"), (WEBP, "image/webp", "webp")],
)
def test_accepts_real_image_signatures(data: bytes, content_type: str, ext: str) -> None:
    assert validate_avatar(data) == (content_type, ext)


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"", "empty_file"),
        (b"GIF89a" + b"\x00" * 16, "unsupported_type"),  # GIF deliberately unsupported
        (b"<svg xmlns='...'/>", "unsupported_type"),  # SVG = script vector, never
    ],
)
def test_rejects_bad_uploads(data: bytes, code: str) -> None:
    with pytest.raises(AvatarError) as excinfo:
        validate_avatar(data)
    assert excinfo.value.code == code


def test_rejects_oversized_avatar() -> None:
    # Test file too large without including the massive binary in parametrize
    large_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * (MAX_AVATAR_BYTES + 1)
    with pytest.raises(AvatarError) as excinfo:
        validate_avatar(large_data)
    assert excinfo.value.code == "too_large"


def test_object_keys_are_random_and_extension_typed() -> None:
    first, second = avatar_object_key("png"), avatar_object_key("png")
    assert first != second
    assert first.startswith("avatars/") and first.endswith(".png")


def test_phone_last4() -> None:
    from modules.identity.phone import phone_last4

    assert phone_last4("+919876543210") == "3210"
