"""JSON log shape, PII redaction, request-id stamping."""

import json
import logging
from typing import Any

import pytest

from shared.telemetry import (
    REDACTED,
    JsonFormatter,
    PiiScrubFilter,
    request_id_var,
    scrub,
)


def make_record(msg: str, args: tuple[Any, ...] | None = None) -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )


def render(record: logging.LogRecord) -> dict[str, Any]:
    PiiScrubFilter().filter(record)
    payload: dict[str, Any] = json.loads(JsonFormatter().format(record))
    return payload


@pytest.mark.parametrize(
    "text",
    [
        "call me at +91 98765 43210",
        "call me at 9876543210",
        "landline 044-2345-6789 ext",
    ],
)
def test_phone_numbers_redacted(text: str) -> None:
    assert REDACTED in scrub(text)
    assert "98765" not in scrub(text)
    assert "2345" not in scrub(text)


def test_email_redacted() -> None:
    out = scrub("farmer contact: ravi.kumar+farm@example.co.in done")
    assert out == f"farmer contact: {REDACTED} done"


def test_log_line_with_phone_shows_redacted() -> None:
    payload = render(make_record("user %s called", ("+919876543210",)))
    assert payload["msg"] == f"user {REDACTED} called"


def test_json_payload_shape() -> None:
    payload = render(make_record("hello"))
    assert set(payload) >= {"ts", "level", "logger", "msg", "request_id"}
    assert payload["level"] == "INFO"
    assert payload["request_id"] is None


def test_request_id_stamped() -> None:
    token = request_id_var.set("req-abc-123")
    try:
        assert render(make_record("x"))["request_id"] == "req-abc-123"
    finally:
        request_id_var.reset(token)


def test_extra_fields_merged_and_scrubbed() -> None:
    record = make_record("request")
    record.extra_fields = {"path": "/users/9876543210", "status": 200}
    payload = render(record)
    assert payload["status"] == 200
    assert payload["path"] == f"/users/{REDACTED}"


def test_short_numbers_not_redacted() -> None:
    assert scrub("status 200 in 42ms on port 55432") == "status 200 in 42ms on port 55432"
