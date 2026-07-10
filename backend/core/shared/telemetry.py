"""Structured JSON logging: request-id context, PII scrubbing, env-driven level.

One JSON object per line on stdout. The PII filter is attached to the handler
so no logger bypasses it; over-redaction is preferred to leakage. Request
bodies and query strings are never logged anywhere in this service (auth and
future PII-bearing routes) — do not add them to extra_fields.
"""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

REDACTED = "[REDACTED]"
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# 10-15 digits with optional + and separators: Indian mobiles (+91 98765 43210)
# and STD landlines. The lookarounds reject matches bounded by hex letters or
# dashes so digit runs inside UUIDs (request ids, entity ids) stay greppable.
_PHONE = re.compile(r"(?<![0-9A-Za-z-])\+?(?:\d[\s\-().]?){9,14}\d(?![0-9A-Za-z-])")


def scrub(text: str) -> str:
    """Redact email addresses and phone numbers."""
    return _PHONE.sub(REDACTED, _EMAIL.sub(REDACTED, text))


class PiiScrubFilter(logging.Filter):
    """Collapse printf args into the message, then redact PII patterns."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = scrub(record.getMessage())
        record.args = None
        fields = getattr(record, "extra_fields", None)
        if isinstance(fields, dict):
            record.extra_fields = {
                key: scrub(value) if isinstance(value, str) else value
                for key, value in fields.items()
            }
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        fields = getattr(record, "extra_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(PiiScrubFilter())
    root = logging.getLogger()
    # replace only our own previous handler: reconfiguring must be idempotent
    # without evicting foreign handlers (pytest's caplog, notably)
    root.handlers = [h for h in root.handlers if not isinstance(h.formatter, JsonFormatter)]
    root.addHandler(handler)
    root.setLevel(level.upper())
    # our JSON access line (shared/request_context.py) replaces uvicorn's
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
