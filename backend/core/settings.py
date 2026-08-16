"""Application settings loaded from the environment via pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = False
    log_level: str = "INFO"

    # Sentry is READY BUT INACTIVE: no SENTRY_DSN in the environment means
    # init_sentry() is a no-op. Activation: docs/runbooks/monitoring.md.
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.1
    release: str = ""  # git sha, baked into images as the RELEASE env var

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # dev-only defaults; real values come from the environment
    # compose maps postgres to host port 55432 (5432 collides with native installs)
    # Runtime role (D12): app_rt has no UPDATE/DELETE on schema audit - the
    # audit log's append-only guarantee is a grant, not a convention. The
    # admin URL (table owner) is for alembic and the test harness only.
    database_url: str = "postgresql+asyncpg://app_rt:app_rt@localhost:55432/agri"
    database_admin_url: str = "postgresql+asyncpg://app:app@localhost:55432/agri"
    redis_url: str = "redis://localhost:6379/0"
    meilisearch_url: str = "http://localhost:7700"
    meilisearch_master_key: str = ""
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"  # dev-only default, matches compose
    minio_secret_key: str = "minioadmin"  # dev-only default, matches compose
    minio_bucket: str = "agri-media"
    # D17 catalog media. Dev default is the MinIO path-style bucket URL;
    # prod supplies the R2/CDN media domain via the environment. Task 6
    # builds the upload path - this task only needs the URL builder final.
    media_public_base_url: str = "http://localhost:9000/agri-media"

    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # OTP (D07). The pepper keys the HMAC over stored code hashes: a DB dump
    # alone must not allow offline brute-force of the 10^6 code space. The
    # default is for dev only; prod supplies OTP_PEPPER via the environment.
    otp_pepper: str = "dev-only-pepper"

    # OAuth2 authorization server (D08). The issuer is the id.agri.in origin
    # baked into every access token's iss claim. The signing key is an RSA
    # private key PEM supplied via the environment; when empty in dev/test an
    # ephemeral keypair is generated per process (tokens die on restart), and
    # in prod an empty key is a hard startup error. Extra public keys keep
    # retired kids resolvable in JWKS during rotation overlap
    # (docs/runbooks/jwks-rotation.md).
    oauth_issuer: str = "https://id.agri.in"
    oauth_jwt_private_key_pem: str = ""
    oauth_jwt_kid: str = "dev-1"
    oauth_jwt_extra_public_keys_pem: str = ""

    # E2E-only escape hatch (D09): mounts GET /auth/otp/_peek returning the
    # mock driver's last code so Playwright can log in across processes.
    # Never on in prod: main.create_app() refuses to mount it there.
    otp_test_peek: bool = False

    # SMS driver flag. "mock" is the default everywhere until DLT registration
    # clears; the MSG91 driver (and its webhook route) is unreachable unless
    # this is flipped to "msg91" in the environment.
    sms_provider: Literal["mock", "msg91"] = "mock"
    msg91_auth_key: str = ""
    msg91_sender_id: str = ""
    msg91_webhook_secret: str = ""
    # DLT template ID slots, one per OTP purpose (filled after DLT approval)
    msg91_template_login: str = ""
    msg91_template_verify_email: str = ""
    msg91_template_sensitive_action: str = ""

    # Notify engine (D12). Email is mock by default; the ZeptoMail driver is
    # additionally gated by the notify.email_enabled DB flag. The hourly cap
    # is the harassment brake from the threat model.
    email_provider: Literal["mock", "zeptomail"] = "mock"
    zeptomail_token: str = ""
    zeptomail_from: str = "no-reply@agri.in"
    notify_user_hourly_cap: int = 30
    notify_worker_enabled: bool = True
    # Web push (D28). Empty keys select the mock driver (kill switch); real
    # sends are additionally gated by the notify.push_enabled DB flag.
    vapid_public_key: str = ""  # base64url ECDSA P-256 (applicationServerKey)
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:no-reply@agri.in"

    # Contact reveal (D18.C, anti-scraping). Public business/branch reads
    # never carry phone/whatsapp; a logged-in user reveals a branch's
    # numbers through a capped endpoint. The cap is the scraping defence.
    contact_reveal_daily_cap: int = 10

    # Post-my-need (D25). The daily cap is the spam brake (fail-closed like
    # the reveal cap); the fanout limit bounds vendor-inbox flooding per
    # posted need.
    need_post_daily_cap: int = 5
    need_fanout_limit: int = 10

    # Business reports (M1.5 trust & safety). Daily cap is the brigading
    # brake (fail-closed like the reveal cap); one-pending-per-target is a
    # DB partial unique index, not a setting.
    report_daily_cap: int = 5

    # Profile-view beacon (D26 analytics-lite). The secret salts the ads-style
    # daily-rotating viewer pseudonym; dedupe is the DB unique index, so a
    # missing Redis costs nothing here.
    # dev-only default; set a real secret in prod.
    view_beacon_secret: str = "dev-view-beacon-secret"

    # Location resolution (D19). GeoIP is optional, state-level, advisory-only
    # infrastructure: an empty path means the feature is off (no mmdb file is
    # committed to this repo; the owner provisions one on the VPS later).
    # trust_forwarded_for gates whether the caller may read X-Forwarded-For
    # for the client IP - only safe behind a trusted reverse proxy.
    geoip_mmdb_path: str = ""
    trust_forwarded_for: bool = False

    # Billing (D20). Razorpay KYC is on hold: every credential defaults empty
    # and the billing_enabled DB flag (seeded false in D03) is the master
    # kill switch - flag off means 404s everywhere and zero live calls.
    # Dunning timers are config: retry offsets are CUMULATIVE hours from
    # past_due_since; after the last offset a grace window runs before
    # cancellation.
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    razorpay_plan_id_growth: str = ""  # filled after KYC + plan creation
    razorpay_plan_id_pro: str = ""
    dunning_retry_hours: str = "24,72,168"
    dunning_grace_days: int = 7
    billing_worker_enabled: bool = True
    gst_rate_bp: int = 1800  # M5 GST on ad sales, basis points
    # M5 Task 9: canned Razorpay responses for create_payment_link/
    # fetch_payment/fetch_payment_link, short-circuiting before any network
    # call. e2e-only escape hatch (D09 otp_test_peek precedent) - NEVER set
    # this in prod; it exists so E2E can exercise checkout without real
    # Razorpay credentials.
    razorpay_test_stub: bool = False
    # M5 Task 9: the advertiser console origin the Payment Link's
    # callback_url bounces back to after hosted checkout.
    console_base_url: str = "http://localhost:3002"
    # M5 Task 12: seller particulars shown on ad-order GST invoice PDFs.
    # Empty in dev is fine (invoice_pdf.py renders "-" for a blank GSTIN);
    # ops fills these in before the first real advertiser is invoiced.
    gst_seller_gstin: str = ""
    gst_seller_name: str = "Oneuni Technologies"
    gst_seller_address: str = ""

    # D21 ads
    ads_worker_enabled: bool = True
    ads_beacon_secret: str = "dev-ads-beacon-secret"  # dev-only default
    ads_freq_cap_per_day: int = 3

    # M3 delivery
    ads_local_boost: float = 2.0  # local-targeted placements x this in rotation (item 8)
    ads_delivery_log_sample: float = 0.1  # why-served log sampling rate (M3.E)

    # --- M4: automatic pincode tiers (geo) -------------------------------
    # Percentile cut points over the pincode population distribution,
    # descending: T1 >= p99, T2 >= p90, T3 >= p60, T4 >= p25, T5 below.
    # Thresholds live in config, not code (spec M4.B).
    pincode_tier_percentiles: str = "99,90,60,25"
    # Verified users (phone-verified + active) needed before a pincode's
    # method flips to population+users. Defends signup farming (threat M4).
    pincode_tier_user_threshold: int = 100
    # Tiers a threshold-crossing pincode is promoted by (bounded at T1).
    pincode_tier_user_promotion_step: int = 1
    # Hysteresis (threat: tier flapping): never auto-demote in v1, and at
    # most one automatic tier change per pincode per interval.
    pincode_tier_promote_only: bool = True
    pincode_tier_min_change_interval_hours: int = 24
    # Sanity floor: refuse to classify a distribution smaller than this
    # (threat: bad/partial source data). Tests lower it via env.
    pincode_tier_min_rows: int = 100
    # Kill switch for scripts/geo_tier_nightly.py.
    geo_tier_job_enabled: bool = True

    # --- A-U2 W1: weather (Open-Meteo) ----------------------------------
    # Open-Meteo needs no API key on the free tier, but the base URL is
    # config so tests point at a local double and a future self-hosted
    # instance is an env change, not a deploy (spec A-U2 W1).
    open_meteo_base_url: str = "https://api.open-meteo.com"
    open_meteo_timeout_seconds: float = 8.0
    # One retry only: this call sits in a public request path behind a
    # cache; a long retry budget would turn an upstream slowdown into our
    # own latency. A miss serves stale (honest degradation) instead.
    open_meteo_retries: int = 1
    # Fresh window per pincode. 30 min matches the upstream model refresh
    # cadence; below that we would burn quota for identical numbers.
    weather_cache_ttl_seconds: int = 1800
    # Last-known-good retention. An upstream outage inside this window
    # serves the previous payload with its real (stale) as-of stamp
    # visible; past it, the weather section goes empty rather than lie.
    weather_stale_ttl_seconds: int = 86400

    # --- A-U2 W2: mandi prices (Agmarknet via data.gov.in) --------------
    # Empty by default and NEVER committed: the client refuses to call
    # without it. Supplied through the environment (SOPS-managed once the
    # age keypair exists — docs/runbooks/secrets.md).
    data_gov_api_key: str = ""
    data_gov_timeout_seconds: float = 20.0
    data_gov_retries: int = 3
    # The state the daily pull ingests. Tamil Nadu is the launch
    # geography (geo.pincodes is TN-only); widening this is a config
    # change, not a code change.
    mandi_ingest_state: str = "Tamil Nadu"
    # Quality gate: a modal price this many times the trailing median is
    # quarantined for review rather than rendered (spec W2).
    mandi_outlier_factor: float = 10.0
    mandi_median_window_days: int = 30
    # Kill switch for scripts/mandi_pull.py.
    mandi_ingest_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
