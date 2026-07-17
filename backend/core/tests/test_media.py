"""D16 shared media helper: re-encode to fresh JPEG so EXIF/GPS metadata is
stripped by construction (non-negotiable: evidence carries no device/location
metadata). Pure unit tests - no storage, no DB."""

from io import BytesIO

import pytest
from PIL import Image

from shared.media import MAX_IMAGE_BYTES, MediaError, reencode_image


def _jpeg_with_exif() -> bytes:
    img = Image.new("RGB", (32, 32), "red")
    exif = Image.Exif()
    exif[0x0110] = "SpyCam 3000"  # Model
    exif[0x013B] = "someone"  # Artist
    buf = BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGBA", (16, 16), (0, 128, 0, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _webp() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (16, 16), "blue").save(buf, format="WEBP")
    return buf.getvalue()


def _gif() -> bytes:
    buf = BytesIO()
    Image.new("P", (16, 16)).save(buf, format="GIF")
    return buf.getvalue()


def _huge_dimensions_small_bytes() -> bytes:
    # 8000x7000 = 56MP: over MAX_IMAGE_PIXELS (40MP) but under Pillow's own
    # open()-time DecompressionBombError threshold (2x = 80MP), so this must
    # be caught by the header-based pixel check, not Pillow's own guard. A
    # uniform 1-bit image compresses to well under MAX_IMAGE_BYTES as PNG -
    # bytes pass the size check, dimensions must trip the pixel check BEFORE
    # decode.
    buf = BytesIO()
    Image.new("1", (8000, 7000)).save(buf, format="PNG")
    return buf.getvalue()


def test_reencode_strips_exif() -> None:
    source = _jpeg_with_exif()
    assert dict(Image.open(BytesIO(source)).getexif())  # premise: EXIF present
    data, content_type = reencode_image(source)
    assert content_type == "image/jpeg"
    out = Image.open(BytesIO(data))
    assert out.format == "JPEG"
    assert dict(out.getexif()) == {}


def test_png_and_webp_normalise_to_jpeg() -> None:
    for source in (_png(), _webp()):
        data, content_type = reencode_image(source)
        assert content_type == "image/jpeg"
        assert Image.open(BytesIO(data)).format == "JPEG"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"", "empty_file"),
        (b"\xff\xd8\xff" + b"0" * MAX_IMAGE_BYTES, "too_large"),
        (b"%PDF-1.7 not an image", "unsupported_type"),
    ],
    ids=["empty_file", "too_large", "unsupported_type"],
)
def test_rejects_bad_input(payload: bytes, code: str) -> None:
    with pytest.raises(MediaError) as excinfo:
        reencode_image(payload)
    assert excinfo.value.code == code


def test_rejects_gif_even_though_pillow_can_open_it() -> None:
    with pytest.raises(MediaError) as excinfo:
        reencode_image(_gif())
    assert excinfo.value.code == "unsupported_type"


def test_rejects_huge_dimensions_before_decode() -> None:
    payload = _huge_dimensions_small_bytes()
    assert len(payload) < MAX_IMAGE_BYTES  # premise: bytes pass the size check
    # 56MP sits in Pillow's 1x-2x warning band: open() warns, our guard raises
    with pytest.warns(Image.DecompressionBombWarning), pytest.raises(MediaError) as excinfo:
        reencode_image(payload)
    assert excinfo.value.code == "too_large"
