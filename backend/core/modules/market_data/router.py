"""Market Data module routes. Endpoints land in later specs."""

from shared.security import SecureRouter

router = SecureRouter(prefix="/market_data", tags=["market_data"])
