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
from modules.coins.admin_router import admin_router as coins_admin_router
from modules.coins.router import router as coins_router
from modules.content.router import router as content_router
from modules.directory.admin_router import admin_router as directory_admin_router
from modules.directory.catalog_admin_router import admin_router as catalog_admin_router
from modules.directory.catalog_router import router as catalog_router
from modules.directory.claims_router import router as directory_claims_router
from modules.directory.reviews_router import router as reviews_router
from modules.directory.router import router as directory_router
from modules.identity.admin_router import admin_router as identity_admin_router
from modules.identity.oauth_keys import get_signing_key
from modules.identity.oauth_router import oauth_router as identity_oauth_router
from modules.identity.profile_router import profile_router as identity_profile_router
from modules.identity.router import msg91_webhook_router, otp_test_peek_router
from modules.identity.router import otp_router as identity_otp_router
from modules.identity.router import router as identity_router
from modules.identity.session_auth import resolve_principal
from modules.identity.session_router import session_router as identity_session_router
from modules.leads.router import router as leads_router
from modules.market_data.router import router as market_data_router
from modules.notify.router import router as notify_router
from modules.notify.worker import run_worker
from modules.search.router import router as search_router
from settings import get_settings
from shared.cache import check_cache, close_redis
from shared.db import check_database
from shared.metrics import render
from shared.middleware import SlugRedirectMiddleware
from shared.request_context import RequestContextMiddleware
from shared.security import SecureRouter, register_principal_resolver
from shared.sentry import init_sentry
from shared.storage import check_storage
from shared.telemetry import configure_logging, get_logger

logger = get_logger(__name__)

MODULE_ROUTERS = [
    ads_router,
    ai_router,
    billing_router,
    catalog_router,
    catalog_admin_router,
    coins_admin_router,
    coins_router,
    content_router,
    directory_admin_router,
    directory_router,
    directory_claims_router,
    identity_admin_router,
    identity_router,
    identity_oauth_router,
    identity_otp_router,
    identity_profile_router,
    identity_session_router,
    leads_router,
    market_data_router,
    notify_router,
    reviews_router,
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


metrics_router = SecureRouter(tags=["observability"])


@metrics_router.get("/metrics", public=True)
async def metrics() -> Response:
    body, content_type = render()
    return Response(content=body, media_type=content_type)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    # fail at boot, not first token: prod without a signing key must not start
    get_signing_key()
    logger.info("public routes: %s", app.state.public_routes)
    worker_stop: asyncio.Event | None = None
    worker_task: asyncio.Task[None] | None = None
    if settings.notify_worker_enabled and settings.app_env != "test":
        worker_stop = asyncio.Event()
        worker_task = asyncio.create_task(run_worker(worker_stop))
    yield
    if worker_stop is not None and worker_task is not None:
        worker_stop.set()
        await worker_task
    await close_redis()


def create_app() -> FastAPI:
    init_sentry(get_settings())
    register_principal_resolver(resolve_principal)  # D09: real session auth
    app = FastAPI(title="agri core", lifespan=lifespan)
    app.add_middleware(SlugRedirectMiddleware)
    # added last so it runs outermost: every request gets an id before
    # anything else, and the access line covers slug redirects too
    app.add_middleware(RequestContextMiddleware)
    routers = [health_router, metrics_router, *MODULE_ROUTERS]
    if get_settings().sms_provider == "msg91":
        # the delivery webhook exists only when the real driver is active;
        # default (mock) builds expose exactly the routes in public_routes.txt
        routers.append(msg91_webhook_router())
    if get_settings().otp_test_peek and get_settings().app_env != "prod":
        # E2E-only OTP peek (D09); the prod guard is a hard AND, not config
        routers.append(otp_test_peek_router())
    public_routes: list[str] = []
    for router in routers:
        app.include_router(router)
        public_routes.extend(router.public_paths)
    app.state.public_routes = public_routes
    return app


app = create_app()
