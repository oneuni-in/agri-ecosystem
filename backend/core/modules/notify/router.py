"""Notify module routes. Endpoints land in later specs."""

from shared.security import SecureRouter

router = SecureRouter(prefix="/notify", tags=["notify"])
