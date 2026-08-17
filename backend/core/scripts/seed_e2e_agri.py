"""Deterministic agri Today data for e2e. Run: python -m scripts.seed_e2e_agri

A-U2 W3. Once the fixtures were deleted, the home's Today sections became
functions of (a) a live Open-Meteo call and (b) whatever the Agmarknet
ingest happens to have. Neither is acceptable in a test run: the first
makes CI depend on an external service that we would also be rude to poll
on every push, and the second is empty on a Sunday.

So this seeds the two REAL inputs instead of faking any code path:

  1. The weather CACHE, with a response captured from the live Open-Meteo
     API. `get_weather` reads its normal cache and never makes a network
     call — the code under test is the production path, unchanged.
  2. market.price_rows, through the REAL ingest (`ingest_records`), so the
     quality gate, the natural-key upsert and the qtl→kg conversion are
     all exercised exactly as they are in production.

Nothing here is invented data: both payloads are recordings of real
responses, and they enter through the same doors real data does.

NEVER runs in prod — the same hard guard as the other e2e escape hatches
(otp_test_peek, razorpay_test_stub).
"""

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from modules.content.models import KIND_GUIDE, KIND_VIDEO, ContentItem  # noqa: E402
from modules.content.service import APPROVED, create_item, set_moderation  # noqa: E402
from modules.market_data import service  # noqa: E402
from modules.market_data.agmarknet import parse_record  # noqa: E402
from modules.market_data.ingest import ingest_records  # noqa: E402
from modules.market_data.open_meteo import _parse  # noqa: E402
from modules.market_data.weather import now_ist  # noqa: E402
from settings import get_settings  # noqa: E402
from shared.db import get_sessionmaker  # noqa: E402

PINCODE = "641001"

# Captured from api.open-meteo.com/v1/forecast for the Coimbatore centroid.
# Dates are relative-free on purpose: the strip labels come from the ISO
# days below, so the seeded run is byte-stable for screenshot diffing.
FORECAST_BODY: dict[str, Any] = {
    "latitude": 10.931458,
    "longitude": 77.0062,
    "timezone": "Asia/Kolkata",
    "current": {
        "time": "2026-08-16T08:15",
        "temperature_2m": 25.5,
        "relative_humidity_2m": 77,
        "weather_code": 3,
        "wind_speed_10m": 20.9,
        "wind_direction_10m": 222,
    },
    "hourly": {
        "time": ["2026-08-16T07:00", "2026-08-16T08:00", "2026-08-16T09:00"],
        "soil_temperature_6cm": [25.1, 25.9, 26.4],
    },
    "daily": {
        "time": [
            "2026-08-13",
            "2026-08-14",
            "2026-08-15",
            "2026-08-16",
            "2026-08-17",
            "2026-08-18",
            "2026-08-19",
            "2026-08-20",
            "2026-08-21",
            "2026-08-22",
        ],
        "weather_code": [61, 3, 51, 3, 51, 3, 51, 53, 3, 3],
        "temperature_2m_max": [30.1, 31.0, 30.6, 32.3, 31.8, 31.8, 31.6, 31.7, 31.9, 31.5],
        "temperature_2m_min": [22.0, 22.2, 22.1, 22.3, 22.6, 22.4, 22.1, 22.4, 21.8, 21.6],
        "precipitation_sum": [4.2, 0.0, 1.1, 0.0, 0.2, 0.0, 0.7, 2.7, 0.0, 0.0],
        "precipitation_probability_max": [70, 20, 45, 57, 57, 80, 100, 98, 39, 31],
        "wind_gusts_10m_max": [60.0, 58.0, 61.0, 65.2, 61.6, 55.1, 55.4, 55.1, 63.4, 58.3],
    },
}

# Real Agmarknet rows (same feed capture the unit tests use), re-districted
# to Coimbatore so they land in the e2e visitor's area. Three commodities
# so the mandi row, ticker and sparklines all have something to render.
_BASE = {
    "state": "Tamil Nadu",
    "district": "Coimbatore",
    "market": "Coimbatore market",
    "variety": "Local",
    "grade": "FAQ",
}
PRICE_ROWS: list[dict[str, Any]] = [
    {
        **_BASE,
        "commodity": c,
        "arrival_date": day,
        "min_price": lo,
        "max_price": hi,
        "modal_price": modal,
    }
    for c, series in (
        ("Paddy(Common)", [(2300, 2350, 2300), (2380, 2410, 2400)]),
        ("Onion", [(2700, 2800, 2750), (2550, 2650, 2600)]),
        ("Groundnut", [(6800, 6900, 6850), (7000, 7200, 7100)]),
    )
    for day, (lo, hi, modal) in zip(("14/08/2026", "15/08/2026"), series, strict=True)
]


async def _main() -> int:
    settings = get_settings()
    if settings.app_env == "prod":
        print("refusing to seed e2e data in prod")  # noqa: T201
        return 1

    # 1. Prime the weather cache so get_weather serves without a network call.
    forecast = _parse(json.loads(json.dumps(FORECAST_BODY)))
    await service._cache_put(PINCODE, forecast, now_ist())

    # 2. Ingest the price rows through the real gate.
    async with get_sessionmaker()() as session:
        result = await ingest_records(
            session,
            [r for r in (parse_record(row) for row in PRICE_ROWS) if r is not None],
        )
        await session.commit()

    # 3. Approved content, so /knowledge is auditable.
    #
    # This is the one place anything gets approved without a human, and it
    # is deliberately narrow: the function refuses outside a test env, the
    # items are transparently labelled fixtures, and they exist so the
    # Lighthouse gate has a populated page to score.
    #
    # /knowledge 404s when nothing is approved — the honesty rule, and the
    # right behaviour in production. But it means CI, which has an empty
    # content table, was auditing a 404 and failing for the wrong reason.
    # Seeding a real approved row is the honest fix; loosening the page to
    # render an empty shell just to satisfy an audit would not be.
    content = await _seed_content()

    print(  # noqa: T201
        f"agri e2e seed: weather cached for {PINCODE};"
        f" prices written={result.written} quarantined={result.quarantined};"
        f" content approved={content}"
    )
    return 0


# (slug, kind, title, summary, extra) — obviously fixtures, never mistakable
# for editorial copy. One video so the card's play/duration treatment is on
# the audited page too.
_E2E_CONTENT: list[tuple[str, str, str, str, dict[str, Any]]] = [
    (
        "e2e-fixture-kharif-sowing-note",
        KIND_GUIDE,
        "E2E fixture — kharif sowing note",
        "Deterministic fixture row for the e2e and Lighthouse runs.",
        {},
    ),
    (
        "e2e-fixture-drip-irrigation-clip",
        KIND_VIDEO,
        "E2E fixture — drip irrigation clip",
        "Deterministic fixture row exercising the video card treatment.",
        {
            "video_provider": "youtube",
            "video_id": "e2eFixtureVid",
            "duration_seconds": 372,
            "language": "ta",
        },
    ),
]


async def _seed_content() -> int:
    """Create + approve the fixture rows. Idempotent on slug."""
    approved = 0
    async with get_sessionmaker()() as session:
        for slug, kind, title, summary, extra in _E2E_CONTENT:
            existing = await session.scalar(select(ContentItem).where(ContentItem.slug == slug))
            item = existing or await create_item(
                session,
                kind=kind,
                slug=slug,
                title={"en": title},
                summary={"en": summary},
                source_name="agri.in e2e fixture",
                source_url="https://agri.in/",
                published_at=datetime(2026, 8, 17, tzinfo=UTC),
                verticals=[],
                states=[],
                **extra,
            )
            # Approve through the real service call, not a raw UPDATE — the
            # fixture should travel the same path a human approval does.
            await set_moderation(session, item.id, status=APPROVED)
            approved += 1
        await session.commit()
    return approved


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
