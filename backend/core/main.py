"""FastAPI application factory for the agri core service."""

import asyncio
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from modules.ads import lifecycle as ads_lifecycle
from modules.ads.admin_router import admin_router as ads_admin_router
from modules.ads.moderation_sources import register_ads_moderation_sources
from modules.ads.router import router as ads_router
from modules.ads.selfserve_router import router as ads_selfserve_router
from modules.ads.service import campaign_billing_ref, pause_active_campaigns
from modules.ai.router import router as ai_router
from modules.billing.ad_orders import campaign_charged_paise
from modules.billing.admin_router import admin_router as billing_admin_router
from modules.billing.payments_admin_router import admin_router as payments_admin_router
from modules.billing.router import router as billing_router
from modules.coins.admin_router import admin_router as coins_admin_router
from modules.coins.dpdp_providers import coins_export
from modules.coins.router import router as coins_router
from modules.content.admin_router import admin_router as content_admin_router
from modules.content.router import router as content_router
from modules.directory.admin_router import admin_router as directory_admin_router
from modules.directory.catalog_admin_router import admin_router as catalog_admin_router
from modules.directory.catalog_router import router as catalog_router
from modules.directory.claims_router import router as directory_claims_router
from modules.directory.dpdp_providers import (
    directory_export,
)
from modules.directory.dpdp_providers import (
    erase as directory_erase,
)
from modules.directory.dpdp_providers import (
    erasure_hold as directory_erasure_hold,
)
from modules.directory.dpdp_providers import (
    reveal_log as directory_reveal_log,
)
from modules.directory.leads_router import router as leads_engine_router
from modules.directory.lookups import business_is_servable, business_ref, owned_business_refs
from modules.directory.moderation_sources import register_directory_moderation_sources
from modules.directory.needs_router import router as needs_router
from modules.directory.reviews_admin_router import admin_router as reviews_admin_router
from modules.directory.reviews_admin_router import reply_admin_router as review_replies_admin_router
from modules.directory.reviews_router import router as reviews_router
from modules.directory.router import router as directory_router
from modules.directory.service import BusinessDisabledError
from modules.education.router import router as education_router
from modules.identity.admin_router import admin_router as identity_admin_router
from modules.identity.dpdp_admin_router import dpdp_admin_router as identity_dpdp_admin_router
from modules.identity.dpdp_providers import identity_export
from modules.identity.dpdp_router import dpdp_router as identity_dpdp_router
from modules.identity.location_router import location_router as identity_location_router
from modules.identity.lookups import notify_contact, public_handle
from modules.identity.oauth_keys import get_signing_key
from modules.identity.oauth_router import oauth_router as identity_oauth_router
from modules.identity.profile_router import profile_router as identity_profile_router
from modules.identity.router import msg91_webhook_router, otp_test_peek_router
from modules.identity.router import otp_router as identity_otp_router
from modules.identity.router import router as identity_router
from modules.identity.session_auth import resolve_principal
from modules.identity.session_router import session_router as identity_session_router
from modules.leads.router import router as leads_router
from modules.market_data.admin_router import admin_router as market_admin_router
from modules.market_data.router import router as market_data_router
from modules.notify.router import router as notify_router
from modules.notify.worker import run_worker
from modules.ops.admin_router import admin_router as ops_admin_router
from modules.search.router import router as search_router
from settings import get_settings
from shared.cache import check_cache, close_redis
from shared.db import check_database
from shared.dpdp import (
    register_eraser,
    register_erasure_hold_provider,
    register_export_provider,
    register_reveal_log_provider,
)
from shared.lookups import (
    register_business_resolver,
    register_campaign_billing_resolver,
    register_campaign_charged_resolver,
    register_campaign_pauser,
    register_campaign_payment_hook,
    register_contact_resolver,
    register_handle_resolver,
    register_owned_businesses_resolver,
    register_servable_resolver,
)
from shared.metrics import render
from shared.middleware import SlugRedirectMiddleware
from shared.request_context import RequestContextMiddleware
from shared.security import SecureRouter, register_principal_resolver
from shared.sentry import init_sentry
from shared.startup_checks import check_production_secrets
from shared.storage import check_storage
from shared.telemetry import configure_logging, get_logger

logger = get_logger(__name__)

MODULE_ROUTERS = [
    ads_admin_router,
    ads_router,
    ads_selfserve_router,
    ai_router,
    billing_router,
    billing_admin_router,
    payments_admin_router,
    catalog_router,
    catalog_admin_router,
    coins_admin_router,
    coins_router,
    content_router,
    content_admin_router,
    directory_admin_router,
    directory_router,
    directory_claims_router,
    education_router,
    identity_admin_router,
    identity_router,
    identity_oauth_router,
    identity_otp_router,
    identity_dpdp_admin_router,
    identity_dpdp_router,
    identity_profile_router,
    identity_session_router,
    leads_router,
    leads_engine_router,
    needs_router,
    market_admin_router,
    market_data_router,
    notify_router,
    ops_admin_router,
    reviews_admin_router,
    review_replies_admin_router,
    reviews_router,
    search_router,
    identity_location_router,
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
    # before anything else: prod must not run on a credential published in
    # this repo. First so the operator sees the actionable list rather than
    # whichever downstream guard happens to trip.
    check_production_secrets(settings)
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


def wire_dependencies() -> None:
    """Register every cross-module seam.

    Called by create_app() AND by any standalone script that touches these
    seams. It is a separate function because a script that imports a service
    directly gets an EMPTY registry, and for the DPDP erasure job that meant
    no hold provider answered, "nobody objected" was indistinguishable from
    "nobody was asked", and a live account was erased that should have been
    held. shared.dpdp now fails closed on an empty registry as well - this
    function is the other half of that fix.
    """
    register_principal_resolver(resolve_principal)  # D09: real session auth
    # D20: dependency-inverted cross-module lookups (same pattern as the
    # principal resolver) - directory owns business refs, identity owns
    # notify contacts; billing consumes both through shared.lookups.
    register_business_resolver(business_ref)
    register_owned_businesses_resolver(owned_business_refs)
    register_contact_resolver(notify_contact)
    # ID-U1: identity owns agri_id, so every module that needs to NAME a user
    # asks through this seam rather than reading identity.users. Coins is the
    # first caller (the login referral banner names the inviter).
    register_handle_resolver(public_handle)
    # ID-U1 W4: the three DPDP rights span every module, and identity may
    # not read anyone else's tables - so each module registers its own
    # answers here and identity's dpdp_router only calls what it finds.
    # Adding a module that holds user data means adding it HERE; the
    # export completeness test asserts the registered set, so a module
    # that forgets shows up as a failing assertion rather than as a
    # quietly short archive handed to someone exercising a legal right.
    register_export_provider("identity", identity_export)
    register_export_provider("directory", directory_export)
    register_export_provider("coins", coins_export)
    register_reveal_log_provider(directory_reveal_log)
    register_erasure_hold_provider("directory", directory_erasure_hold)
    register_eraser("directory", directory_erase)
    # M1.5: directory answers serve-time status (ads consume it - the M3
    # seam); ads pause an advertiser's campaigns when directory disables it.
    register_servable_resolver(business_is_servable)
    register_campaign_pauser(pause_active_campaigns)
    # M5 Task 9: billing's checkout route (modules/billing/ad_orders.py)
    # reads a campaign's price snapshot and ownership through this resolver
    # - the same dependency-inversion seam as the pauser above.
    register_campaign_billing_resolver(campaign_billing_ref)
    # M5 Task 7: billing's webhook (Task 10) tells ads about paid/refunded
    # events through this hook - the payment half of the activation gate.
    register_campaign_payment_hook(ads_lifecycle.on_payment_event)
    # M5 Task 13 fast-follow: ads' campaign stats route reads net retained
    # ledger money through this seam instead of the mutable
    # budget_serves_total/used columns (which a refund overwrites as a
    # serve-exhaustion trick, not a real budget).
    register_campaign_charged_resolver(campaign_charged_paise)
    # D21: unified moderation queue - owning modules register their sources
    # (same dependency-inversion pattern as the resolvers above).
    register_directory_moderation_sources()
    register_ads_moderation_sources()


def create_app() -> FastAPI:
    init_sentry(get_settings())
    wire_dependencies()
    app = FastAPI(title="agri core", lifespan=lifespan)

    # M1.5.B: the disabled-business console lock surfaces from every
    # owner-scoped route via service.get_owned_business - one app-level
    # mapping instead of N per-route excepts.
    async def _business_disabled_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": "business_disabled"})

    app.add_exception_handler(BusinessDisabledError, _business_disabled_handler)
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
