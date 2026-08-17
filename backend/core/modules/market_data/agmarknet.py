"""Agmarknet daily prices via data.gov.in (A-U2 W2).

VERIFIED AGAINST THE LIVE API (2026-08-16). What the probes established,
because every one of these shapes the code below:

  - Resource 9ef84268-… "Current Daily Price of Various Commodities from
    Various Markets (Mandi)" publishes: state, district, market,
    commodity, variety, grade, arrival_date (DD/MM/YYYY), min_price,
    max_price, modal_price. Prices are RUPEES PER QUINTAL.

  - There is NO arrivals/quantity field. The frozen contract's
    `arrivals_qtl` is nullable and stays null; the spec's "arrivals where
    provided" resolves to "not provided".

  - THE ROW CAP IS SILENT. Asking for limit=1000 returns ten rows and
    echoes `"limit": 10` — no error, no warning. Code that trusts the
    requested limit will silently ingest 10 rows and believe it has
    everything. Paging by row offset is therefore mandatory, and the
    walk stops on `total`, never on "I asked for everything".

  - THE DATE FILTER IS SILENTLY IGNORED. filters[arrival_date]=01/07/2026
    returns rows dated 16/08/2026 — the full unfiltered set. Only
    keyword-typed fields (state, district, market, commodity) actually
    filter. This is why there is no date-range fetch here: the endpoint
    cannot express one.

  - Keyword filters are case-INSENSITIVE on this resource today
    ("andhra pradesh" matched "Andhra Pradesh"). The D03 note recorded
    case-sensitivity, so we still send the published spelling rather
    than depend on the leniency continuing.

  - The feed fills through the day, state by state: at 08:48 IST only 58
    rows nationwide existed, from six states, none of them Tamil Nadu.
    A pull scheduled too early gets an almost empty day. See
    scripts/mandi_pull.py.

The API key is read from the environment and is never committed
(settings.data_gov_api_key, empty by default -> the client refuses to
call rather than leaking a request without one).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import httpx

from settings import get_settings
from shared.telemetry import get_logger

logger = get_logger(__name__)

BASE_URL = "https://api.data.gov.in"

# NOT COSMETIC — THE REQUEST HANGS WITHOUT IT.
# data.gov.in blackholes httpx's default User-Agent ("python-httpx/…"):
# the connection is accepted and then nothing is ever sent back, so the
# call dies on the read timeout with no status code and no error to
# explain it. Measured 2026-08-16: identical request, default UA -> 4
# consecutive 26s timeouts; with an explicit UA -> a response in under a
# second. curl works out of the box, which is exactly why this looks
# like "the API is down" when it is not.
#
# This is an honest identifier, not an impersonation: it names the
# client and where to complain about it, which is what a polite reader
# of a public API should send.
USER_AGENT = "agri.in-mandi-ingest/1.0 (+https://agri.in)"
# "Current Daily Price of Various Commodities from Various Markets (Mandi)"
DAILY_RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"

# Rows requested per page. THE CEILING IS PER-KEY, not global: the public
# sample key silently truncates to 10 (echoing "limit": 10 as if you had
# asked for it), while a registered key honours large limits — measured
# 2026-08-17, limit=2000 returned 2000 rows. Tamil Nadu alone publishes
# ~5.8k rows a day, so paging at 10 would be ~580 requests where 6 will
# do, and hammering a public API 580 times a day to work around a
# restriction we no longer have would be rude as well as slow.
#
# The walk below never TRUSTS this number, though — see fetch_day. It
# advances by however many rows actually came back, so a downgraded key
# (or a server that quietly caps again) costs extra requests, never
# silently-missing data.
PAGE_SIZE = 1000
# Bounds the walk so a feed that reports an absurd `total` — or one that
# keeps returning rows — cannot spin forever.
MAX_PAGES = 2000


class AgmarknetError(RuntimeError):
    """Transport failure, timeout, non-2xx, or a missing API key."""


@dataclass(frozen=True, slots=True)
class PriceRecord:
    state: str
    district: str
    market: str
    commodity: str
    variety: str
    grade: str
    arrival_date: date
    min_price_qtl: Decimal
    max_price_qtl: Decimal
    modal_price_qtl: Decimal


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_record(raw: dict[str, Any]) -> PriceRecord | None:
    """One feed row -> PriceRecord, or None if it is unusable.

    Returning None (rather than raising) keeps one malformed row from
    aborting a whole day's ingest; the caller counts skips.
    """
    try:
        arrival = datetime.strptime(str(raw.get("arrival_date", "")), "%d/%m/%Y").date()
    except ValueError:
        return None

    low = _decimal(raw.get("min_price"))
    high = _decimal(raw.get("max_price"))
    modal = _decimal(raw.get("modal_price"))
    if low is None or high is None or modal is None:
        return None

    state = str(raw.get("state") or "").strip()
    market = str(raw.get("market") or "").strip()
    commodity = str(raw.get("commodity") or "").strip()
    if not (state and market and commodity):
        return None

    return PriceRecord(
        state=state,
        district=str(raw.get("district") or "").strip(),
        market=market,
        commodity=commodity,
        variety=str(raw.get("variety") or "").strip(),
        grade=str(raw.get("grade") or "").strip(),
        arrival_date=arrival,
        min_price_qtl=low,
        max_price_qtl=high,
        modal_price_qtl=modal,
    )


async def _get_page(
    client: httpx.AsyncClient, params: dict[str, str], attempts: int
) -> dict[str, Any]:
    """One page with bounded exponential backoff.

    Being a polite client to a public government API matters more than
    finishing fast: a 429 or a 5xx is waited out, not hammered.
    """
    delay = 1.0
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            response = await client.get(f"/resource/{DAILY_RESOURCE}", params=params)
            if response.status_code in (429, 500, 502, 503, 504):
                raise AgmarknetError(f"agmarknet -> {response.status_code}")
            if response.status_code >= 400:
                raise AgmarknetError(f"agmarknet -> {response.status_code}")
            return cast(dict[str, Any], response.json())
        except (httpx.HTTPError, AgmarknetError, ValueError) as exc:
            last = exc
            logger.warning(
                "market.agmarknet_page_failed",
                extra={"extra_fields": {"attempt": attempt + 1, "exc_type": type(exc).__name__}},
            )
            if attempt + 1 < attempts:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)
    raise AgmarknetError(f"agmarknet page failed: {type(last).__name__}")


async def fetch_day(
    *, state: str | None = None, page_pause_seconds: float = 0.4
) -> list[PriceRecord]:
    """Every row the feed currently publishes, optionally one state.

    "Currently" is the whole vocabulary this endpoint has: it serves the
    live day and cannot be asked for another one (see module docstring).
    """
    settings = get_settings()
    if not settings.data_gov_api_key:
        raise AgmarknetError("data_gov_api_key is not configured")

    params: dict[str, str] = {
        "api-key": settings.data_gov_api_key,
        "format": "json",
        "limit": str(PAGE_SIZE),
    }
    if state:
        params["filters[state]"] = state

    records: list[PriceRecord] = []
    skipped = 0
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=settings.data_gov_timeout_seconds,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        first = await _get_page(client, params | {"offset": "0"}, settings.data_gov_retries + 1)
        total = int(first.get("total") or 0)
        pages = [first]

        # Advance by rows ACTUALLY RETURNED, never by PAGE_SIZE. The
        # server may hand back fewer than asked for — silently, echoing a
        # limit it did not honour — and stepping by the requested size
        # would then skip every row in the gap. Stepping by the real count
        # is correct under any cap, including one that changes mid-walk.
        #
        # Sequential, not concurrent: one polite reader, and the offset
        # walk needs a stable ordering anyway.
        seen = len(first.get("records") or [])
        for _page_index in range(1, MAX_PAGES):
            if seen >= total or seen == 0:
                break
            await asyncio.sleep(page_pause_seconds)
            page = await _get_page(
                client, params | {"offset": str(seen)}, settings.data_gov_retries + 1
            )
            rows = len(page.get("records") or [])
            if rows == 0:
                # Nothing left despite `total` claiming otherwise: stop
                # rather than loop on an offset that yields nothing.
                break
            pages.append(page)
            seen += rows

    for page in pages:
        for raw in page.get("records") or []:
            record = parse_record(raw)
            if record is None:
                skipped += 1
            else:
                records.append(record)

    logger.info(
        "market.agmarknet_fetched",
        extra={"extra_fields": {"records": len(records), "skipped": skipped, "total": total}},
    )
    return records
