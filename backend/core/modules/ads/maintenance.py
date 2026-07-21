"""Daily partition pre-create for ads.impressions/ads.clicks (D21).

Runs on the ADMIN engine (partition DDL is owner work; app_rt has no CREATE
- the DB-identity split is deliberate). The DEFAULT partition in 0022 is the
backstop if this never runs; this keeps day-partition pruning effective."""

from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

PARTITIONED_TABLES = ("impressions", "clicks")


def partition_name(table: str, day: date) -> str:
    return f"{table}_p{day:%Y%m%d}"


async def ensure_partitions(
    conn: AsyncConnection, *, start: date, days_ahead: int = 7
) -> list[str]:
    """Create daily partitions start..start+days_ahead. Idempotent; returns
    only the names actually created this call."""
    created: list[str] = []
    for table in PARTITIONED_TABLES:
        for offset in range(days_ahead + 1):
            day = start + timedelta(days=offset)
            name = partition_name(table, day)
            exists = await conn.scalar(
                text("SELECT to_regclass(:qualified) IS NOT NULL"),
                {"qualified": f"ads.{name}"},
            )
            if exists:
                continue
            nxt = day + timedelta(days=1)
            await conn.execute(
                text(
                    f'CREATE TABLE IF NOT EXISTS ads."{name}" '
                    f"PARTITION OF ads.{table} "
                    f"FOR VALUES FROM ('{day.isoformat()}') TO ('{nxt.isoformat()}')"
                )
            )
            created.append(name)
    return created
