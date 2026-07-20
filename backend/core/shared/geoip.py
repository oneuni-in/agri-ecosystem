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
    # Advisory-only, and called from a public endpoint (D19 Task 7): any
    # malformed/unexpected mmdb record shape - a null "country", a
    # "subdivisions" that isn't a list, a non-dict subdivision/names entry -
    # must degrade to None, never raise. One broad guard around the whole
    # reader-call-plus-parse is simpler and more robust than isinstance-
    # checking every traversal step individually.
    try:
        rec = reader.get(ip)
        if not isinstance(rec, dict):
            return None
        if (rec.get("country") or {}).get("iso_code") != "IN":
            return None
        subdivisions = rec.get("subdivisions") or []
        names = subdivisions[0].get("names", {})
        name = names.get("en")
        return name if isinstance(name, str) else None
    except Exception:
        return None


def reset_geoip() -> None:
    global _reader, _load_failed
    if _reader is not None:
        with contextlib.suppress(Exception):
            _reader.close()
    _reader = None
    _load_failed = False
