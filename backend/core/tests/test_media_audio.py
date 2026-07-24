"""Voice-note shell validation (D25): magic-byte sniff + size cap, no
transcode. The client-declared MIME is ignored - the container magic decides."""

import pytest

from shared import media

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64
OGG = b"OggS" + b"\x00" * 64
M4A = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 64


@pytest.mark.parametrize(
    ("blob", "mime"),
    [(WEBM, "audio/webm"), (OGG, "audio/ogg"), (M4A, "audio/mp4")],
)
def test_accepts_known_audio_containers(blob: bytes, mime: str) -> None:
    data, out_mime = media.validate_audio(blob)
    assert data == blob  # stored as-is: shell, not transcode
    assert out_mime == mime
    assert media.AUDIO_EXTENSIONS[out_mime] in {"webm", "ogg", "m4a"}


def test_rejects_empty() -> None:
    with pytest.raises(media.MediaError) as exc:
        media.validate_audio(b"")
    assert exc.value.code == "empty_file"


def test_rejects_oversize() -> None:
    with pytest.raises(media.MediaError) as exc:
        media.validate_audio(b"\x1a\x45\xdf\xa3" + b"\x00" * media.MAX_AUDIO_BYTES)
    assert exc.value.code == "too_large"


def test_rejects_non_audio_magic() -> None:
    # a JPEG must NOT sneak through the audio path (and vice versa)
    with pytest.raises(media.MediaError) as exc:
        media.validate_audio(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    assert exc.value.code == "unsupported_type"


def test_rejects_truncated_header() -> None:
    with pytest.raises(media.MediaError) as exc:
        media.validate_audio(b"Og")
    assert exc.value.code == "unsupported_type"
