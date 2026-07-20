"""Optional IP -> state (subdivision) lookup. State-level only, advisory only.

Provisioning the GeoLite2 mmdb is an owner/VPS action; unset path = feature off.
"""

import contextlib
import ipaddress
import logging
from typing import Any

from settings import get_settings

logger = logging.getLogger(__name__)
_reader: Any | None = None
_load_failed = False


def _get_reader() -> Any | None:
    global _reader, _load_failed
    if _reader is not None or _load_failed:
        return _reader
    path = get_settings().geoip_mmdb_path
    if not path:
        _load_failed = True
        return None
    try:
        import maxminddb

        _reader = maxminddb.open_database(path)
    except Exception:
        logger.warning("geoip.open_failed", extra={"extra_fields": {"path": path}})
        _load_failed = True
    return _reader


def state_for_ip(ip: str) -> str | None:
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return None
    reader = _get_reader()
    if reader is None:
        return None
    try:
        rec = reader.get(ip)
    except Exception:
        return None
    if not isinstance(rec, dict):
        return None
    if rec.get("country", {}).get("iso_code") != "IN":
        return None
    subdivisions = rec.get("subdivisions") or []
    if not subdivisions:
        return None
    names = subdivisions[0].get("names", {})
    name = names.get("en")
    return name if isinstance(name, str) else None


def reset_geoip() -> None:
    global _reader, _load_failed
    if _reader is not None:
        with contextlib.suppress(Exception):
            _reader.close()
    _reader = None
    _load_failed = False
