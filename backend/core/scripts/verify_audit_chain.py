"""Verify the audit hash chain; exit 1 on any break (cron/CI job, D12).

Runs as the runtime role (SELECT is enough). Cron wiring is deferred with the
VPS work; until then this is invoked manually or from CI.
"""

import asyncio
import sys

from shared.audit import verify_chain
from shared.db import get_sessionmaker
from shared.metrics import AUDIT_CHAIN_BREAKS, AUDIT_CHAIN_DAYS_VERIFIED
from shared.telemetry import configure_logging, get_logger

logger = get_logger(__name__)


async def main() -> int:
    async with get_sessionmaker()() as session:
        breaks = await verify_chain(session)
    if not breaks:
        AUDIT_CHAIN_DAYS_VERIFIED.labels("ok").inc()
        logger.info("audit chain verified", extra={"extra_fields": {"breaks": 0}})
        return 0
    AUDIT_CHAIN_DAYS_VERIFIED.labels("broken").inc()
    for item in breaks:
        AUDIT_CHAIN_BREAKS.labels(item.reason).inc()
        logger.error(
            "audit chain break",
            extra={
                "extra_fields": {
                    "day": item.day.isoformat(),
                    "seq": item.seq,
                    "reason": item.reason,
                }
            },
        )
    return 1


if __name__ == "__main__":
    configure_logging("INFO")
    sys.exit(asyncio.run(main()))
