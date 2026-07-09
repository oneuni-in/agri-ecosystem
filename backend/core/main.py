"""FastAPI application factory for the agri core service."""

import asyncio
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Response
from pydantic import BaseModel

from modules.ads.router import router as ads_router
from modules.ai.router import router as ai_router
from modules.billing.router import router as billing_router
from modules.coins.router import router as coins_router
from modules.content.router import router as content_router
from modules.directory.router import router as directory_router
from modules.identity.router import router as identity_router
from modules.leads.router import router as leads_router
from modules.market_data.router import router as market_data_router
from modules.notify.router import router as notify_router
from modules.search.router import router as search_router
from settings import get_settings
from shared.cache import check_cache, close_redis
from shared.db import check_database
from shared.security import SecureRouter
from shared.storage import check_storage
from shared.telemetry import configure_logging, get_logger

logger = get_logger(__name__)

MODULE_ROUTERS = [
    ads_router,
    ai_router,
    billing_router,
    coins_router,
    content_router,
    directory_router,
    identity_router,
    leads_router,
    market_data_router,
    notify_router,
    search_router,
]


class HealthResponse(BaseModel):
    status: str


class DeepHealthResponse(BaseModel):
    status: str
    services: dict[str, bool]


health_router = SecureRouter(tags=["health"])


@health_router.get("/health", public=True)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


async def _check_meilisearch() -> bool:
    url = f"{get_settings().meilisearch_url}/health"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


async def _bounded(check: Awaitable[bool]) -> bool:
    try:
        return await asyncio.wait_for(check, timeout=2.0)
    except Exception:
        return False


@health_router.get("/health/deep", public=True)
async def health_deep(response: Response) -> DeepHealthResponse:
    names = ["postgres", "redis", "meilisearch", "minio"]
    results = await asyncio.gather(
        _bounded(check_database()),
        _bounded(check_cache()),
        _bounded(_check_meilisearch()),
        _bounded(check_storage()),
    )
    services = dict(zip(names, results, strict=True))
    healthy = all(services.values())
    if not healthy:
        response.status_code = 503
    return DeepHealthResponse(status="ok" if healthy else "degraded", services=services)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("public routes: %s", app.state.public_routes)
    yield
    await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(title="agri core", lifespan=lifespan)
    public_routes: list[str] = []
    for router in [health_router, *MODULE_ROUTERS]:
        app.include_router(router)
        public_routes.extend(router.public_paths)
    app.state.public_routes = public_routes
    return app


app = create_app()
