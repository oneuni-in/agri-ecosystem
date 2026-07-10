# D05 — Observability + Backups + Gate 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Structured observability (Sentry, JSON logs with PII scrubbing, request-id tracing, Prometheus-format metrics, pg_stat_statements), an age-encrypted pg_dump backup pipeline with a **really-executed, timed restore drill** against the local Docker Postgres, ready-but-inactive Uptime Kuma/R2 wiring, 11 ADRs, per-module CLAUDE.md files, and the Gate 1 evidence pack (fresh-clone timing, insecure-endpoint CI failure demo) — culminating in tag v0.1.0.

**Architecture:** Everything activates via environment only: no Sentry DSN → no-op (and zero client bytes, protecting Lighthouse gates); no R2 credentials → local-only backups; Kuma compose file exists but is never started. The backend gains one new middleware (request context: request-id + JSON access log + metrics) and one module (`shared/metrics.py`). The restore drill is executed for real against the `agri-dev` Postgres container and its measured timings are committed.

**Tech Stack:** FastAPI + sentry-sdk[fastapi] + prometheus-client (backend); @sentry/nextjs + a new `@agri/observability` workspace package (frontend); bash + `age` + `pg_dump -Fc` (backups); Uptime Kuma via compose (inactive).

## Global Constraints

- Toolchain: Node 24 / pnpm 11 / Tailwind 3; host Python is **3.12** (`backend/core/.venv`, `pip install -e .[dev]`), Docker truth is 3.13. No uv, no gh CLI.
- Branch `feat/d05-observability` from `dev`. Conventional commits. PR targets `dev`. NEVER push to dev/main.
- Backend cwd for all tooling is `backend/core`. Gate: `ruff format --check .`, `ruff check .`, `mypy .` (strict), `lint-imports`, `python scripts/migrate_check.py`, `pytest -q`.
- Import rules: modules never import each other; shared never imports modules.
- Every endpoint on `SecureRouter`; a new `public=True` route requires adding it to `backend/core/public_routes.txt` in the same PR.
- New global state needs a reset hook in `tests/conftest.py` (`_reset_state`).
- Migrations need the `# -- THREAT/NOTES:` docstring block (downgrade data loss / locks / rollout) and must survive `migrate_check.py` up/down/up.
- Tokens only in app code — no raw hex (`node scripts/check-hex.mjs` gate).
- Lighthouse gate (D04): only `/` of each app and web-agri `/demo` are audited. Do not change thresholds; do not add client-side JS weight to audited pages.
- pnpm 11 blocks postinstall build scripts unless listed in `pnpm-workspace.yaml` `allowBuilds`.
- **DO NOT** log request bodies or query strings anywhere. **DO NOT** ship a Prometheus/Grafana server. **DO NOT** simulate the restore drill — run it.
- VPS/Hostinger is deferred and owner-driven: all VPS-facing pieces (Kuma live monitors, R2 upload, nightly cron, WAL archiving, Netdata) ship ready-but-inactive with runbook activation notes. Never start them.
- Postgres dev container: compose project `agri-dev`, host port **55432**, user/db `app`/`agri`.
- Windows host: bash scripts run under Git Bash; use `set -euo pipefail`; docker exec pipes work.

---

### Task 1: Structured JSON logging + PII scrub filter (`telemetry.py`)

**Files:**
- Create branch first: `git checkout dev && git pull && git checkout -b feat/d05-observability`
- Modify: `backend/core/shared/telemetry.py` (full rewrite, currently 15 lines)
- Test: `backend/core/tests/test_telemetry.py` (new)

**Interfaces:**
- Produces: `request_id_var: ContextVar[str | None]`, `scrub(text: str) -> str`, `REDACTED = "[REDACTED]"`, `PiiScrubFilter`, `JsonFormatter`, `configure_logging(level: str) -> None`, `get_logger(name) -> logging.Logger` (unchanged signature). Log records may carry `extra={"extra_fields": {...}}` — merged into the JSON payload, string values scrubbed.

- [ ] **Step 1: Write the failing tests** — `backend/core/tests/test_telemetry.py`:

```python
"""JSON log shape, PII redaction, request-id stamping."""

import json
import logging

import pytest

from shared.telemetry import (
    REDACTED,
    JsonFormatter,
    PiiScrubFilter,
    request_id_var,
    scrub,
)


def make_record(msg: str, args: tuple | None = None) -> logging.LogRecord:
    return logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg=msg, args=args, exc_info=None,
    )


def render(record: logging.LogRecord) -> dict:
    PiiScrubFilter().filter(record)
    return json.loads(JsonFormatter().format(record))


@pytest.mark.parametrize(
    "text",
    [
        "call me at +91 98765 43210",
        "call me at 9876543210",
        "landline 044-2345-6789 ext",
    ],
)
def test_phone_numbers_redacted(text: str) -> None:
    assert REDACTED in scrub(text)
    assert "98765" not in scrub(text)
    assert "2345" not in scrub(text)


def test_email_redacted() -> None:
    out = scrub("farmer contact: ravi.kumar+farm@example.co.in done")
    assert out == f"farmer contact: {REDACTED} done"


def test_log_line_with_phone_shows_redacted() -> None:
    payload = render(make_record("user %s called", ("+919876543210",)))
    assert payload["msg"] == f"user {REDACTED} called"


def test_json_payload_shape() -> None:
    payload = render(make_record("hello"))
    assert set(payload) >= {"ts", "level", "logger", "msg", "request_id"}
    assert payload["level"] == "INFO"
    assert payload["request_id"] is None


def test_request_id_stamped() -> None:
    token = request_id_var.set("req-abc-123")
    try:
        assert render(make_record("x"))["request_id"] == "req-abc-123"
    finally:
        request_id_var.reset(token)


def test_extra_fields_merged_and_scrubbed() -> None:
    record = make_record("request")
    record.extra_fields = {"path": "/users/9876543210", "status": 200}  # type: ignore[attr-defined]
    payload = render(record)
    assert payload["status"] == 200
    assert payload["path"] == f"/users/{REDACTED}"


def test_short_numbers_not_redacted() -> None:
    assert scrub("status 200 in 42ms on port 55432") == "status 200 in 42ms on port 55432"
```

- [ ] **Step 2: Run to verify failure**

Run (cwd `backend/core`): `.venv/Scripts/python.exe -m pytest tests/test_telemetry.py -v`
Expected: FAIL — `ImportError: cannot import name 'REDACTED'`.

- [ ] **Step 3: Rewrite `backend/core/shared/telemetry.py`:**

```python
"""Structured JSON logging: request-id context, PII scrubbing, env-driven level.

One JSON object per line on stdout. The PII filter is attached to the handler
so no logger bypasses it; over-redaction is preferred to leakage. Request
bodies and query strings are never logged anywhere in this service (auth and
future PII-bearing routes) — do not add them to extra_fields.
"""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

REDACTED = "[REDACTED]"
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# 10-15 digits with optional + and separators: Indian mobiles (+91 98765 43210)
# and STD landlines. The lookarounds stop matches starting/ending mid-number.
_PHONE = re.compile(r"(?<!\d)\+?(?:\d[\s\-().]?){9,14}\d(?!\d)")


def scrub(text: str) -> str:
    """Redact email addresses and phone numbers."""
    return _PHONE.sub(REDACTED, _EMAIL.sub(REDACTED, text))


class PiiScrubFilter(logging.Filter):
    """Collapse printf args into the message, then redact PII patterns."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = scrub(record.getMessage())
        record.args = None
        fields = getattr(record, "extra_fields", None)
        if isinstance(fields, dict):
            record.extra_fields = {  # type: ignore[attr-defined]
                key: scrub(value) if isinstance(value, str) else value
                for key, value in fields.items()
            }
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        fields = getattr(record, "extra_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(PiiScrubFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # our JSON access line (shared/request_context.py) replaces uvicorn's
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
```

- [ ] **Step 4: Run tests + gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_telemetry.py -v` → all PASS.
Then: `ruff format . && ruff check . && mypy .` → clean. If the phone regex over/under-matches a test case, fix the regex, not the test.

- [ ] **Step 5: Commit**

```bash
git add backend/core/shared/telemetry.py backend/core/tests/test_telemetry.py
git commit -m "feat(d05): structured JSON logging with PII scrub filter"
```

---

### Task 2: Request-context middleware (request-id + JSON access log)

**Files:**
- Create: `backend/core/shared/request_context.py`
- Modify: `backend/core/main.py` (add middleware in `create_app`)
- Test: `backend/core/tests/test_request_context.py`

**Interfaces:**
- Consumes: `request_id_var`, `get_logger` (Task 1). Calls `shared.metrics.observe_request(...)` — **in this task create it as a stub that Task 3 fills**.
- Produces: `REQUEST_ID_HEADER = "x-request-id"`, `RequestContextMiddleware`. Response always carries `x-request-id`; a valid inbound header (`[A-Za-z0-9_-]{8,64}`) is reused, anything else replaced with a fresh UUIDv7. One JSON access line per request: `method`, `path` (no query string), `route` (matched template), `status`, `duration_ms`.

- [ ] **Step 1: Stub metrics** — create `backend/core/shared/metrics.py`:

```python
"""Prometheus-format process metrics. Filled in by the metrics task (D05)."""


def observe_request(method: str, route: str, status: int, seconds: float) -> None:
    pass
```

- [ ] **Step 2: Write the failing tests** — `backend/core/tests/test_request_context.py`:

```python
"""Request-id propagation, response header, JSON access log line."""

import json
import logging

from fastapi.testclient import TestClient

from main import create_app
from shared.request_context import REQUEST_ID_HEADER
from shared.telemetry import JsonFormatter, PiiScrubFilter


def client() -> TestClient:
    return TestClient(create_app())


def test_response_carries_generated_request_id() -> None:
    response = client().get("/health")
    rid = response.headers.get(REQUEST_ID_HEADER)
    assert rid and len(rid) == 36  # uuid7 string


def test_inbound_request_id_is_echoed() -> None:
    response = client().get("/health", headers={REQUEST_ID_HEADER: "trace-me-12345"})
    assert response.headers[REQUEST_ID_HEADER] == "trace-me-12345"


def test_invalid_inbound_id_is_replaced() -> None:
    hostile = "abc def\n<script>"
    response = client().get("/health", headers={REQUEST_ID_HEADER: hostile})
    assert response.headers[REQUEST_ID_HEADER] != hostile


def test_access_log_line_is_json_with_request_id(caplog) -> None:
    handler_filter = PiiScrubFilter()
    with caplog.at_level(logging.INFO, logger="agri.access"):
        client().get("/health", headers={REQUEST_ID_HEADER: "trace-me-12345"})
    record = next(r for r in caplog.records if r.name == "agri.access")
    handler_filter.filter(record)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["request_id"] == "trace-me-12345"
    assert payload["method"] == "GET"
    assert payload["path"] == "/health"
    assert payload["route"] == "/health"
    assert payload["status"] == 200
    assert payload["duration_ms"] >= 0
    assert "?" not in payload["path"]
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_request_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shared.request_context'`.

- [ ] **Step 4: Create `backend/core/shared/request_context.py`:**

```python
"""Request-scoped context: request-id propagation, JSON access log, metrics.

The frontend sends x-request-id (packages/observability apiFetch); it is
echoed on the response and stamped on every log line via
telemetry.request_id_var, so one id traces app -> API -> log. Bodies and
query strings are never logged (PII).
"""

import re
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from uuid6 import uuid7

from shared.metrics import observe_request
from shared.telemetry import get_logger, request_id_var

logger = get_logger("agri.access")

REQUEST_ID_HEADER = "x-request-id"
# inbound ids are attacker-controlled: only a sane charset/length reaches logs
_VALID_ID = re.compile(r"[A-Za-z0-9_-]{8,64}")


def _inbound_id(request: Request) -> str:
    supplied = request.headers.get(REQUEST_ID_HEADER, "")
    if _VALID_ID.fullmatch(supplied):
        return supplied
    return str(uuid7())


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = _inbound_id(request)
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            observe_request(request.method, route_path, status, duration_ms / 1000)
            logger.info(
                "request",
                extra={
                    "extra_fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "route": route_path,
                        "status": status,
                        "duration_ms": round(duration_ms, 1),
                    }
                },
            )
            request_id_var.reset(token)
```

- [ ] **Step 5: Wire into `create_app` in `backend/core/main.py`** — add import `from shared.request_context import RequestContextMiddleware` and, in `create_app`, **after** the existing `app.add_middleware(SlugRedirectMiddleware)` line add:

```python
    # added last so it runs outermost: every request gets an id before
    # anything else, and the access line covers slug redirects too
    app.add_middleware(RequestContextMiddleware)
```

- [ ] **Step 6: Run tests + full backend gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_request_context.py tests/test_main.py -v` → PASS (if `test_main.py` asserts on response headers, extend expectations rather than weakening them).
Then `ruff format . && ruff check . && mypy . && lint-imports` → clean.

- [ ] **Step 7: Commit**

```bash
git add backend/core/shared/request_context.py backend/core/shared/metrics.py backend/core/main.py backend/core/tests/test_request_context.py
git commit -m "feat(d05): request-id middleware with JSON access log"
```

---

### Task 3: Metrics — prometheus-client, `/metrics` endpoint

**Files:**
- Modify: `backend/core/pyproject.toml` (add `"prometheus-client>=0.20"` to `[project].dependencies`), then `pip install -e .[dev]`
- Modify: `backend/core/shared/metrics.py` (replace stub)
- Modify: `backend/core/main.py` (metrics router), `backend/core/public_routes.txt` (add `/metrics`)
- Modify: `backend/core/tests/conftest.py` (`_reset_state` calls `reset_metrics()`)
- Test: `backend/core/tests/test_metrics.py`

**Interfaces:**
- Produces: `observe_request(method, route, status, seconds)` (same signature as stub), `render() -> tuple[bytes, str]`, `reset_metrics()`. Metrics: `http_requests_total{method,route,status}`, `http_request_errors_total{method,route}` (5xx only), `http_request_duration_seconds` histogram (p95 derivable from buckets). `GET /metrics` is public.

- [ ] **Step 1: Write the failing tests** — `backend/core/tests/test_metrics.py`:

```python
"""Prometheus endpoint: counters, error counter, histogram buckets."""

from fastapi import Response
from fastapi.testclient import TestClient

from main import create_app
from shared.security import SecureRouter


def test_metrics_endpoint_is_public_prometheus_text() -> None:
    client = TestClient(create_app())
    client.get("/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    assert 'http_requests_total{method="GET",route="/health",status="200"}' in body
    assert "http_request_duration_seconds_bucket" in body


def test_5xx_increments_error_counter() -> None:
    app = create_app()
    boom = SecureRouter()

    @boom.get("/boom", public=True)
    async def boom_route() -> Response:
        raise RuntimeError("boom")

    app.include_router(boom)
    client = TestClient(app, raise_server_exceptions=False)
    client.get("/boom")
    body = client.get("/metrics").text
    assert 'http_request_errors_total{method="GET",route="/boom"}' in body
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_metrics.py -v`
Expected: FAIL — 404 on `/metrics`.

- [ ] **Step 3: Implement.** Replace `backend/core/shared/metrics.py`:

```python
"""Prometheus-format process metrics (D05).

Right-sized per ADR-0011: no Prometheus server ships. Netdata on the VPS (or
any scraper) reads GET /metrics. The route label is always the matched route
template, never the raw path, to bound label cardinality.
"""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

registry = CollectorRegistry()

REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests processed",
    ["method", "route", "status"],
    registry=registry,
)
ERRORS = Counter(
    "http_request_errors_total",
    "HTTP requests that returned a 5xx",
    ["method", "route"],
    registry=registry,
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "Request wall time; p95 is derived from these buckets",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 6.4),
    registry=registry,
)


def observe_request(method: str, route: str, status: int, seconds: float) -> None:
    REQUESTS.labels(method, route, str(status)).inc()
    LATENCY.labels(method, route).observe(seconds)
    if status >= 500:
        ERRORS.labels(method, route).inc()


def render() -> tuple[bytes, str]:
    return generate_latest(registry), CONTENT_TYPE_LATEST


def reset_metrics() -> None:
    """Test hook (tests/conftest.py): drop label children between tests."""
    for metric in (REQUESTS, ERRORS, LATENCY):
        metric.clear()
```

In `backend/core/main.py` add next to `health_router`:

```python
metrics_router = SecureRouter(tags=["observability"])


@metrics_router.get("/metrics", public=True)
async def metrics() -> Response:
    body, content_type = render()
    return Response(content=body, media_type=content_type)
```

with imports `from shared.metrics import render` (and `Response` is already imported from fastapi). Register it in `create_app`'s router loop: `for router in [health_router, metrics_router, *MODULE_ROUTERS]:`.

Append `/metrics` to `backend/core/public_routes.txt` (keep the file's existing ordering convention — check whether it is sorted; match it).

In `tests/conftest.py` add `from shared.metrics import reset_metrics` and call `reset_metrics()` inside `_reset_state` after `rate_limiter.reset()`.

- [ ] **Step 4: Run tests + public-routes gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_metrics.py -v` → PASS.
Run: `.venv/Scripts/python.exe scripts/dump_public_routes.py --check` → exit 0 (proves `/metrics` declared).
Full: `ruff format . && ruff check . && mypy . && lint-imports && python -m pytest -q` → green.

- [ ] **Step 5: Commit**

```bash
git add backend/core/pyproject.toml backend/core/shared/metrics.py backend/core/main.py backend/core/public_routes.txt backend/core/tests/test_metrics.py backend/core/tests/conftest.py
git commit -m "feat(d05): prometheus-format /metrics with latency histogram and error counters"
```

---

### Task 4: Postgres observability — pg_stat_statements + slow-query log

**Files:**
- Modify: `docker-compose.dev.yml` (postgres `command`), `docker-compose.staging.yml` (same block on its postgres service)
- Create: `backend/core/alembic/versions/0006_pg_stat_statements.py`

**Interfaces:**
- Produces: `pg_stat_statements` extension at revision `0006`; server logs any statement >200ms.

- [ ] **Step 1: Compose changes.** In `docker-compose.dev.yml`, add to the `postgres` service (below `image: postgres:16`):

```yaml
    # D05 observability: pg_stat_statements needs a preload; statements
    # slower than 200ms land in the container log (docker logs).
    command:
      - postgres
      - -c
      - shared_preload_libraries=pg_stat_statements
      - -c
      - pg_stat_statements.track=all
      - -c
      - log_min_duration_statement=200ms
```

Mirror the identical block on the `postgres` service in `docker-compose.staging.yml`.

- [ ] **Step 2: Migration.** Create `backend/core/alembic/versions/0006_pg_stat_statements.py`:

```python
"""Enable pg_stat_statements for query observability.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-10

"""
# -- THREAT/NOTES:
# downgrade data loss: drops the extension and its accumulated statistics;
#   nothing application-facing reads them.
# locks: CREATE/DROP EXTENSION touches the catalog momentarily; negligible.
# rollout: querying the pg_stat_statements view needs the server started with
#   shared_preload_libraries=pg_stat_statements (docker-compose command), but
#   CREATE EXTENSION itself does not — CI's plain postgres:16 service applies
#   this revision cleanly.

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_stat_statements")
```

- [ ] **Step 3: Recreate the dev postgres and verify preload took effect**

```bash
docker compose -f docker-compose.dev.yml up -d postgres   # recreates with new command; pgdata volume persists
docker compose -f docker-compose.dev.yml ps               # wait healthy
docker exec agri-dev-postgres-1 psql -U app -d agri -tAc "show shared_preload_libraries"
```
Expected: `pg_stat_statements`.

- [ ] **Step 4: Run migrate_check against the dev DB** (cwd `backend/core`):

Run: `.venv/Scripts/python.exe scripts/migrate_check.py`
Expected: up/down/up passes.

- [ ] **Step 5: CI-parity check — migration must apply WITHOUT preload** (this is what CI's service container looks like):

```bash
docker run -d --name pg-ci-parity -e POSTGRES_USER=app -e POSTGRES_PASSWORD=app -e POSTGRES_DB=agri -p 55440:5432 postgres:16
# wait for: docker exec pg-ci-parity pg_isready -U app -d agri
DATABASE_URL=postgresql+asyncpg://app:app@localhost:55440/agri .venv/Scripts/python.exe scripts/migrate_check.py
docker rm -f pg-ci-parity
```
Expected: passes. If `CREATE EXTENSION` errors without preload, change upgrade to a documented no-op guard — but verify first; it should succeed.

- [ ] **Step 6: Verify slow-query logging + view works**

```bash
docker exec agri-dev-postgres-1 psql -U app -d agri -c "select pg_sleep(0.3)"
docker logs agri-dev-postgres-1 --since 2m | grep "duration:"
docker exec agri-dev-postgres-1 psql -U app -d agri -tAc "select count(*) >= 0 from pg_stat_statements"
```
Expected: a `duration: 3xx.xxx ms` line; the view query returns `t`.

- [ ] **Step 7: Commit**

```bash
git add docker-compose.dev.yml docker-compose.staging.yml backend/core/alembic/versions/0006_pg_stat_statements.py
git commit -m "feat(d05): pg_stat_statements + 200ms slow-query log"
```

---

### Task 5: Backend Sentry (env-driven, release-tagged)

**Files:**
- Modify: `backend/core/pyproject.toml` (add `"sentry-sdk[fastapi]>=2.0"`), `pip install -e .[dev]`
- Modify: `backend/core/settings.py`, `backend/core/main.py`, `backend/core/Dockerfile`
- Modify: `.github/workflows/deploy-staging.yml` (GIT_SHA build-arg)
- Test: `backend/core/tests/test_sentry.py`

**Interfaces:**
- Consumes: `Settings` (new fields `sentry_dsn: str = ""`, `sentry_traces_sample_rate: float = 0.1`, `release: str = ""`).
- Produces: `shared.sentry.init_sentry(settings) -> bool` called at the top of `create_app()`.

- [ ] **Step 1: Failing test** — `backend/core/tests/test_sentry.py`:

```python
"""Sentry is a no-op without a DSN and initialises with one."""

from settings import Settings
from shared.sentry import init_sentry


def test_no_dsn_no_init() -> None:
    assert init_sentry(Settings(sentry_dsn="")) is False


def test_dsn_initialises_with_release_and_env(monkeypatch) -> None:
    settings = Settings(
        sentry_dsn="https://examplePublicKey@o0.ingest.sentry.io/0",
        release="abc123",
        app_env="test",
    )
    assert init_sentry(settings) is True
    import sentry_sdk

    client = sentry_sdk.get_client()
    assert client.options["release"] == "abc123"
    assert client.options["send_default_pii"] is False
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sentry.py -v` → FAIL (`No module named 'shared.sentry'`).

- [ ] **Step 3: Implement.** Add to `Settings` in `backend/core/settings.py` (after `log_level`):

```python
    # Sentry is READY BUT INACTIVE: no SENTRY_DSN in the environment means
    # init_sentry() is a no-op. Activation: docs/runbooks/monitoring.md.
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.1
    release: str = ""  # git sha, baked into images as the RELEASE env var
```

Create `backend/core/shared/sentry.py`:

```python
"""Sentry initialisation: no DSN, no-op — activation is environment-only.

send_default_pii stays False and request bodies are never attached; the log
side of PII hygiene is telemetry.PiiScrubFilter.
"""

import sentry_sdk

from settings import Settings


def init_sentry(settings: Settings) -> bool:
    """Initialise Sentry when a DSN is configured; returns True if it was."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=settings.release or None,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        max_request_body_size="never",
    )
    return True
```

In `main.py` `create_app()` first line: `init_sentry(get_settings())` (import `from shared.sentry import init_sentry`).

In `backend/core/Dockerfile`, next to the existing ENV block of the final stage, add:

```dockerfile
ARG GIT_SHA=""
ENV RELEASE=$GIT_SHA
```

In `.github/workflows/deploy-staging.yml`, extend the shared `build-args:` block of the build-push step:

```yaml
          build-args: |
            APP=${{ matrix.name }}
            GIT_SHA=${{ github.sha }}
```

- [ ] **Step 4: Run tests + gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sentry.py -q && ruff format . && ruff check . && mypy . && lint-imports` → green. (If `client.options` access differs in the installed sentry-sdk version, assert via `sentry_sdk.get_client().is_active()` plus `options["release"]` — check the SDK, don't guess.)

- [ ] **Step 5: Commit**

```bash
git add backend/core/pyproject.toml backend/core/settings.py backend/core/shared/sentry.py backend/core/main.py backend/core/Dockerfile backend/core/tests/test_sentry.py .github/workflows/deploy-staging.yml
git commit -m "feat(d05): env-driven backend sentry with release tagging"
```

---

### Task 6: `@agri/observability` workspace package

**Files:**
- Create: `packages/observability/package.json`, `tsconfig.json`, `eslint.config.mjs`, `vitest.config.ts`, `src/api.ts`, `src/client.ts`, `src/server.ts`, `src/api.test.ts`
- Modify: `pnpm-workspace.yaml` (allowBuilds entry for `@sentry/cli`)

**Interfaces:**
- Produces: `@agri/observability/api` → `REQUEST_ID_HEADER`, `apiUrl(path)`, `apiFetch(path, init?)`; `@agri/observability/client` → `initSentryClient()`; `@agri/observability/server` → `registerSentry()`, `onRequestError`.
- Consumed by Task 7 (all 5 apps) and Task 9 (trace page).

- [ ] **Step 1: Scaffold.** Copy `tsconfig.json` and `eslint.config.mjs` patterns from `packages/auth-client` (adjust include paths only). `packages/observability/package.json` (pin the same versions `packages/ui/package.json` uses for vitest/eslint/typescript; resolve `@sentry/nextjs` with `pnpm --filter @agri/observability add @sentry/nextjs` and keep whatever exact version pnpm pins):

```json
{
  "name": "@agri/observability",
  "version": "0.0.0",
  "private": true,
  "exports": {
    "./api": "./src/api.ts",
    "./client": "./src/client.ts",
    "./server": "./src/server.ts"
  },
  "scripts": {
    "lint": "eslint . --max-warnings 0",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@sentry/nextjs": "<pnpm-pinned>"
  },
  "devDependencies": {
    "@agri/config": "workspace:*",
    "eslint": "9.39.4",
    "typescript": "5.9.3",
    "vitest": "<same as packages/ui>"
  }
}
```

In `pnpm-workspace.yaml` `allowBuilds`, add (keep the file's comment style):

```yaml
  # sentry-cli downloads its binary in postinstall; only needed once source-map
  # upload activates at launch prep (docs/runbooks/monitoring.md). Keep blocked.
  "@sentry/cli": false
```

- [ ] **Step 2: Failing test** — `packages/observability/src/api.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { REQUEST_ID_HEADER, apiFetch, apiUrl } from "./api";

describe("apiFetch", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("stamps a request id when none is given", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("ok"));
    vi.stubGlobal("fetch", fetchMock);
    await apiFetch("/health");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(apiUrl("/health"));
    const rid = new Headers(init.headers).get(REQUEST_ID_HEADER);
    expect(rid).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("preserves a caller-supplied request id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("ok"));
    vi.stubGlobal("fetch", fetchMock);
    await apiFetch("/health", { headers: { [REQUEST_ID_HEADER]: "trace-me-12345" } });
    const [, init] = fetchMock.mock.calls[0];
    expect(new Headers(init.headers).get(REQUEST_ID_HEADER)).toBe("trace-me-12345");
  });
});
```

`vitest.config.ts` — copy `packages/ui/vitest.config.ts`, trimmed to this package's needs.

Run: `pnpm --filter @agri/observability test` → FAIL (api.ts missing).

- [ ] **Step 3: Implement.** `src/api.ts`:

```ts
/**
 * Backend API fetch helper. Stamps x-request-id (uuid) so one id traces
 * app -> API -> log; the backend echoes it on the response
 * (backend/core/shared/request_context.py).
 */
export const REQUEST_ID_HEADER = "x-request-id";

export function apiUrl(path: string): string {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  return new URL(path, base).toString();
}

export async function apiFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  if (!headers.has(REQUEST_ID_HEADER)) {
    headers.set(REQUEST_ID_HEADER, crypto.randomUUID());
  }
  return fetch(apiUrl(path), { ...init, headers });
}
```

`src/client.ts`:

```ts
/**
 * Browser Sentry init. READY BUT INACTIVE: NEXT_PUBLIC_SENTRY_DSN is inlined
 * at build time, so without it the guard is constant-false and the bundler
 * drops the dynamic import chunk — zero client bytes, which keeps the D04
 * Lighthouse perf gate honest. Activation: docs/runbooks/monitoring.md.
 */
export function initSentryClient(): void {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return;
  void import("@sentry/nextjs").then((Sentry) => {
    Sentry.init({
      dsn,
      release: process.env.NEXT_PUBLIC_RELEASE,
      tracesSampleRate: 0.1,
      sendDefaultPii: false,
    });
  });
}
```

`src/server.ts`:

```ts
/**
 * Node-runtime Sentry init for Next instrumentation. Same inactive-without-DSN
 * contract as client.ts. The type-only import is erased at compile time, so
 * loading this module never pulls the SDK in.
 */
import type { captureRequestError } from "@sentry/nextjs";

function dsn(): string | undefined {
  return process.env.SENTRY_DSN ?? process.env.NEXT_PUBLIC_SENTRY_DSN;
}

export async function registerSentry(): Promise<void> {
  const value = dsn();
  if (!value) return;
  const Sentry = await import("@sentry/nextjs");
  Sentry.init({
    dsn: value,
    release: process.env.RELEASE ?? process.env.NEXT_PUBLIC_RELEASE,
    tracesSampleRate: 0.1,
    sendDefaultPii: false,
  });
}

export async function onRequestError(
  ...args: Parameters<typeof captureRequestError>
): Promise<void> {
  if (!dsn()) return;
  const Sentry = await import("@sentry/nextjs");
  Sentry.captureRequestError(...args);
}
```

- [ ] **Step 4: Run** `pnpm --filter @agri/observability test` → PASS, then `pnpm --filter @agri/observability lint typecheck` (or via turbo) → clean.

- [ ] **Step 5: Commit**

```bash
git add packages/observability pnpm-workspace.yaml pnpm-lock.yaml
git commit -m "feat(d05): @agri/observability - apiFetch request-id + lazy sentry init"
```

---

### Task 7: Wire Sentry + instrumentation into all 5 apps

**Files (× 5: web-agri, web-milk, web-organic, web-id, web-admin):**
- Create: `apps/<app>/instrumentation.ts`, `apps/<app>/instrumentation-client.ts`
- Modify: `apps/<app>/next.config.ts`, `apps/<app>/package.json`
- Modify: `apps/Dockerfile` (GIT_SHA → NEXT_PUBLIC_RELEASE/RELEASE)

**Interfaces:**
- Consumes: `@agri/observability/client`, `/server` (Task 6).

- [ ] **Step 1: Per app, identical files.** `apps/<app>/instrumentation-client.ts`:

```ts
import { initSentryClient } from "@agri/observability/client";

initSentryClient();
```

`apps/<app>/instrumentation.ts`:

```ts
export { onRequestError } from "@agri/observability/server";

export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { registerSentry } = await import("@agri/observability/server");
    await registerSentry();
  }
}
```

- [ ] **Step 2: Per app `next.config.ts`.** Add `"@agri/observability"` to `transpilePackages`; add `import { withSentryConfig } from "@sentry/nextjs";` at the top; replace the final `export default withNextIntl(nextConfig);` with:

```ts
const config = withNextIntl(nextConfig);

// Source-map upload is READY BUT INACTIVE: SENTRY_AUTH_TOKEN is a CI secret
// that stays unset until launch prep (docs/runbooks/monitoring.md), so local
// and CI builds skip the wrapper entirely.
export default process.env.SENTRY_AUTH_TOKEN
  ? withSentryConfig(config, {
      org: process.env.SENTRY_ORG,
      project: "agri-web-agri", // per app: agri-web-milk / agri-web-organic / agri-web-id / agri-web-admin
      silent: true,
      widenClientFileUpload: true,
    })
  : config;
```

Per app `package.json`: add `"@agri/observability": "workspace:*"` and `"@sentry/nextjs": "<same pinned version>"` to dependencies, then `pnpm install`.

- [ ] **Step 3: `apps/Dockerfile`.** In the builder stage (near `ENV NEXT_OUTPUT=standalone`) add:

```dockerfile
ARG GIT_SHA=""
ENV NEXT_PUBLIC_RELEASE=$GIT_SHA
```

and in the runtime stage (near `ENV NODE_ENV=production`) add `RELEASE=$GIT_SHA` after re-declaring `ARG GIT_SHA` in that stage.

- [ ] **Step 4: Verify builds are unaffected without a DSN**

Run: `pnpm exec turbo run lint typecheck test build`
Expected: all green. Then confirm zero sentry bytes in an audited page: `grep -ri "sentry" apps/web-agri/.next/static/chunks --include="*.js" -l` → **no matches** (the dynamic import must have been dropped; if chunks appear, the DSN guard isn't being inlined — fix before proceeding, e.g. ensure the check reads `process.env.NEXT_PUBLIC_SENTRY_DSN` literally).

- [ ] **Step 5: Commit**

```bash
git add apps/*/instrumentation.ts apps/*/instrumentation-client.ts apps/*/next.config.ts apps/*/package.json apps/Dockerfile pnpm-lock.yaml
git commit -m "feat(d05): sentry instrumentation in all five apps (inactive without DSN)"
```

---

### Task 8: CI — sentry env passthrough (inactive until secrets exist)

**Files:**
- Modify: `.github/workflows/ci.yml` (web job only)

- [ ] **Step 1:** In the `web` job, add an `env:` block on the turbo step (or job level):

```yaml
        env:
          # sentry source-map upload: inactive until these secrets are set at
          # launch prep (docs/runbooks/monitoring.md); unset -> builds skip it
          SENTRY_AUTH_TOKEN: ${{ secrets.SENTRY_AUTH_TOKEN }}
          SENTRY_ORG: ${{ secrets.SENTRY_ORG }}
```

Do NOT add new required checks; do not touch the lighthouse job (no DSN there keeps audited bundles clean).

- [ ] **Step 2: Validate YAML** — `node -e "console.log('ok')"` isn't enough; run `npx --yes yaml-lint .github/workflows/ci.yml` or `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"` from the repo root using the backend venv python. Expected: parses.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci(d05): pass sentry secrets to web build (inactive until launch prep)"
```

---

### Task 9: Request-id trace demo page (web-agri `/demo/trace`)

**Files:**
- Create: `apps/web-agri/app/demo/trace/page.tsx`

**Interfaces:**
- Consumes: `apiFetch`, `REQUEST_ID_HEADER` from `@agri/observability/api`.
- Produces: the Gate-1 trace evidence (screenshot/log capture used in Task 16).

Only `/` and `/demo` are Lighthouse-audited (scripts/lhci-affected.mjs pushes exactly `/demo`), so this new route is outside the gate. It must still render with the API down (CI builds).

- [ ] **Step 1: Create the page.** Before writing, open `apps/web-agri/app/demo/page.tsx` and reuse its token utility classes (no raw hex; adjust the class names below to what the design system actually provides):

```tsx
import { REQUEST_ID_HEADER, apiFetch } from "@agri/observability/api";

// D05 debug page: proves one request id flows app -> API -> JSON log.
export const dynamic = "force-dynamic";

export const metadata = {
  title: "request-id trace",
  robots: { index: false, follow: false },
};

export default async function TracePage() {
  const requestId = crypto.randomUUID();
  let result = "API unreachable (is `docker compose -f docker-compose.dev.yml up` running?)";
  try {
    const response = await apiFetch("/health", {
      headers: { [REQUEST_ID_HEADER]: requestId },
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
    });
    const echoed = response.headers.get(REQUEST_ID_HEADER);
    result = `HTTP ${response.status} — x-request-id ${
      echoed === requestId ? "echoed by API" : `MISMATCH (${echoed})`
    }`;
  } catch {
    // page must render with the API down (CI builds have no backend)
  }
  return (
    <main className="mx-auto max-w-2xl p-8 font-mono text-sm">
      <h1 className="mb-4 text-lg font-semibold">request-id trace</h1>
      <p>request_id: {requestId}</p>
      <p>API /health: {result}</p>
      <p className="mt-4">
        Verify in the API log: docker compose -f docker-compose.dev.yml logs api | grep
        &lt;request_id&gt;
      </p>
    </main>
  );
}
```

- [ ] **Step 2: Build check** — `pnpm --filter @agri/web-agri build` (with the API stopped) → succeeds.

- [ ] **Step 3: Live demo (evidence for Gate 1).** With `docker compose -f docker-compose.dev.yml up -d` and `pnpm --filter @agri/web-agri dev` running:

```bash
curl -s http://localhost:3002/demo/trace | grep -o "request_id: [0-9a-f-]*"
docker compose -f docker-compose.dev.yml logs api --since 5m | grep "<that id>"
```
Expected: the API's JSON access line contains `"request_id":"<that id>"` and `"route":"/health"`. Save both outputs verbatim — Task 16 pastes them into `docs/runbooks/gate-1.md`. Also capture a PII sample now: `docker compose ... exec api python -c "from settings import get_settings; from shared.telemetry import configure_logging, get_logger; configure_logging('INFO'); get_logger('demo').info('farmer +91 98765 43210 signed up')"` → the printed line shows `[REDACTED]`. Save it.

- [ ] **Step 4: Run app lint/typecheck** — `pnpm exec turbo run lint typecheck --filter=@agri/web-agri` → clean.

- [ ] **Step 5: Commit**

```bash
git add apps/web-agri/app/demo/trace/page.tsx
git commit -m "feat(d05): /demo/trace page proving request-id propagation FE->BE->log"
```

---

### Task 10: Backup scripts (pg_dump + age; R2 ready-but-inactive)

**Files:**
- Create: `scripts/backup/backup.sh`, `scripts/backup/wal-archive.sh`
- Modify: `.gitignore` (add `backups/`)

**Interfaces:**
- Produces: `backups/agri-<UTC stamp>.dump.age` files; env contract `PG_CONTAINER`, `PG_USER`, `PG_DB`, `BACKUP_DIR`, `RETENTION_DAYS`, `AGE_RECIPIENTS_FILE`, and the inactive R2 trio `BACKUP_UPLOAD_ENABLED`/`R2_BUCKET`/`R2_ENDPOINT`. Task 11's restore.sh consumes the same env names.

- [ ] **Step 1: Install age on the host** (needed by the drill): `winget install --id FiloSottile.age --accept-source-agreements --accept-package-agreements`, then new shell → `age --version` works. Fallback: download the Windows binary from the FiloSottile/age GitHub releases into the session scratchpad and use its full path via `AGE_BIN`.

- [ ] **Step 2: Generate the DEV drill keypair** (production keypair is generated offline by the owner — never do it for them):

```bash
age-keygen -o secrets/backup-age-key.txt          # gitignored (secrets/* rule)
grep "public key" secrets/backup-age-key.txt | sed 's/.*: //' > secrets/backup-age-recipients.txt
```

- [ ] **Step 3: Create `scripts/backup/backup.sh`:**

```bash
#!/usr/bin/env bash
# Postgres backup: pg_dump custom format, age-encrypted, optional R2 upload.
# Runs anywhere docker + age exist (dev box now; VPS nightly cron at launch —
# see docs/runbooks/backup-restore.md). R2 upload and the cron schedule are
# READY BUT INACTIVE until launch prep.
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-agri-dev-postgres-1}"
PG_USER="${PG_USER:-app}"
PG_DB="${PG_DB:-agri}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
AGE_BIN="${AGE_BIN:-age}"
AGE_RECIPIENTS_FILE="${AGE_RECIPIENTS_FILE:-secrets/backup-age-recipients.txt}"

[[ -f "$AGE_RECIPIENTS_FILE" ]] || { echo "missing $AGE_RECIPIENTS_FILE (age recipients)"; exit 1; }
mkdir -p "$BACKUP_DIR"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="${BACKUP_DIR}/agri-${stamp}.dump.age"

start="$(date +%s)"
docker exec "$PG_CONTAINER" pg_dump -Fc -U "$PG_USER" "$PG_DB" \
  | "$AGE_BIN" -e -R "$AGE_RECIPIENTS_FILE" -o "$out"
duration="$(( $(date +%s) - start ))"
size="$(du -h "$out" | cut -f1)"
echo "backup: ${out} (${size}) in ${duration}s"

# R2 upload — READY BUT INACTIVE until launch prep (docs/runbooks/backup-restore.md).
# Activation: set BACKUP_UPLOAD_ENABLED=1 + R2_BUCKET + R2_ENDPOINT and configure
# the aws CLI with R2 credentials; the bucket's 30-day lifecycle rule handles
# remote retention.
if [[ "${BACKUP_UPLOAD_ENABLED:-0}" == "1" ]]; then
  : "${R2_BUCKET:?BACKUP_UPLOAD_ENABLED=1 requires R2_BUCKET}"
  : "${R2_ENDPOINT:?BACKUP_UPLOAD_ENABLED=1 requires R2_ENDPOINT}"
  aws s3 cp "$out" "s3://${R2_BUCKET}/pg/$(basename "$out")" --endpoint-url "$R2_ENDPOINT"
  echo "uploaded to r2: s3://${R2_BUCKET}/pg/$(basename "$out")"
else
  echo "r2 upload skipped (BACKUP_UPLOAD_ENABLED != 1)"
fi

# local retention
find "$BACKUP_DIR" -name 'agri-*.dump.age' -mtime "+${RETENTION_DAYS}" -delete
```

- [ ] **Step 4: Create `scripts/backup/wal-archive.sh`:**

```bash
#!/usr/bin/env bash
# WAL archive_command target — READY BUT INACTIVE until launch prep.
# Activation (docs/runbooks/backup-restore.md): set in postgres config
#   archive_mode = on
#   archive_command = '/path/to/wal-archive.sh %p %f'
# plus R2_BUCKET/R2_ENDPOINT in the environment and aws CLI credentials.
set -euo pipefail
wal_path="$1"; wal_name="$2"
: "${R2_BUCKET:?wal archiving requires R2_BUCKET}"
: "${R2_ENDPOINT:?wal archiving requires R2_ENDPOINT}"
aws s3 cp "$wal_path" "s3://${R2_BUCKET}/wal/${wal_name}" --endpoint-url "$R2_ENDPOINT"
```

- [ ] **Step 5:** Add to `.gitignore` under the build-output section: `backups/` with comment `# local pg backups (scripts/backup/backup.sh)`.

- [ ] **Step 6: Run it for real**

```bash
bash scripts/backup/backup.sh
ls -lh backups/
```
Expected: one `agri-*.dump.age` file, non-trivial size (the DB holds D03 geo data), a printed duration. Record size + duration for the runbook.

- [ ] **Step 7: Commit** (scripts only — key material and dumps are gitignored; verify with `git status`):

```bash
git add scripts/backup/backup.sh scripts/backup/wal-archive.sh .gitignore
git commit -m "feat(d05): age-encrypted pg_dump backup script, r2 + wal paths inactive"
```

---

### Task 11: `scripts/restore.sh` — restore to a scratch database with verification

**Files:**
- Create: `scripts/restore.sh` (spec-mandated path)

**Interfaces:**
- Consumes: Task 10's env contract + `AGE_KEY_FILE` (default `secrets/backup-age-key.txt`), `SCRATCH_DB` (default `agri_restore_drill`), optional `$1` = dump path (default: newest in `BACKUP_DIR`).
- Produces: scratch DB restored + per-table row-count diff vs source; exits non-zero on any mismatch; prints timing (the measured RTO).

- [ ] **Step 1: Create `scripts/restore.sh`:**

```bash
#!/usr/bin/env bash
# Restore drill: decrypt a backup and restore it into a scratch database,
# then diff per-table row counts against the source DB. Exits non-zero on
# any mismatch. The printed duration is the measured RTO
# (docs/runbooks/backup-restore.md).
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-agri-dev-postgres-1}"
PG_USER="${PG_USER:-app}"
PG_DB="${PG_DB:-agri}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
SCRATCH_DB="${SCRATCH_DB:-agri_restore_drill}"
AGE_BIN="${AGE_BIN:-age}"
AGE_KEY_FILE="${AGE_KEY_FILE:-secrets/backup-age-key.txt}"

dump="${1:-$(ls -1t "$BACKUP_DIR"/agri-*.dump.age | head -1)}"
[[ -f "$dump" ]] || { echo "no backup found in $BACKUP_DIR"; exit 1; }
[[ -f "$AGE_KEY_FILE" ]] || { echo "missing $AGE_KEY_FILE (age identity)"; exit 1; }
echo "restoring: $dump -> $SCRATCH_DB"

psql_db() { docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$1" -v ON_ERROR_STOP=1 -tA -c "$2"; }

counts() { # exact per-table row counts, schema-qualified, sorted
  docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$1" -tA -c \
    "select format('select %L || ''|'' || count(*) from %I.%I',
                   schemaname || '.' || tablename, schemaname, tablename)
       from pg_tables
      where schemaname not in ('pg_catalog', 'information_schema')
      order by 1" \
    | docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$1" -tA -f -
}

start="$(date +%s)"
psql_db postgres "DROP DATABASE IF EXISTS ${SCRATCH_DB} WITH (FORCE)"
psql_db postgres "CREATE DATABASE ${SCRATCH_DB}"
"$AGE_BIN" -d -i "$AGE_KEY_FILE" "$dump" \
  | docker exec -i "$PG_CONTAINER" pg_restore -U "$PG_USER" -d "$SCRATCH_DB" \
      --no-owner --no-privileges
restore_done="$(date +%s)"

src_counts="$(counts "$PG_DB")"
dst_counts="$(counts "$SCRATCH_DB")"
if [[ "$src_counts" != "$dst_counts" ]]; then
  echo "ROW COUNT MISMATCH between $PG_DB and $SCRATCH_DB:"
  diff <(echo "$src_counts") <(echo "$dst_counts") || true
  exit 1
fi
tables="$(echo "$dst_counts" | wc -l | tr -d ' ')"
rows="$(echo "$dst_counts" | awk -F'|' '{s+=$2} END {print s}')"
end="$(date +%s)"

echo "restore:  $(( restore_done - start ))s (drop+create+decrypt+pg_restore)"
echo "verify:   $(( end - restore_done ))s (${tables} tables, ${rows} rows, all counts match)"
echo "total RTO: $(( end - start ))s"
```

- [ ] **Step 2: Run it for real** (this is the pre-drill shakedown; the official timed drill is Task 12):

```bash
bash scripts/restore.sh
```
Expected: ends with `total RTO: <N>s` and exit 0. Debug failures here (docker exec -i on Git Bash may need `MSYS_NO_PATHCONV=1`; if `pg_restore` warns about the pg_stat_statements extension needing superuser, `--no-owner --no-privileges` normally clears it — investigate, don't suppress, anything else).
Negative check: `bash scripts/restore.sh nonexistent.dump.age` → non-zero exit.

- [ ] **Step 3: Commit**

```bash
git add scripts/restore.sh
git commit -m "feat(d05): restore.sh - scratch-db restore with row-count verification"
```

---

### Task 12: RESTORE DRILL #1 (executed, timed) + `docs/runbooks/backup-restore.md`

**Files:**
- Create: `docs/runbooks/backup-restore.md`

This drill is a NON-NEGOTIABLE: run against the real local Docker Postgres, never simulated. (VPS deferral is owner-approved; the runbook notes drill #2 re-runs on the VPS at launch prep.)

- [ ] **Step 1: Fresh timed drill, captured:**

```bash
bash scripts/backup/backup.sh   2>&1 | tee /tmp/drill-backup.log
bash scripts/restore.sh         2>&1 | tee /tmp/drill-restore.log
docker exec agri-dev-postgres-1 psql -U app -d agri_restore_drill -tAc "select count(*) from alembic_version"
docker exec agri-dev-postgres-1 psql -U app -d postgres -c "DROP DATABASE agri_restore_drill WITH (FORCE)"
```
Record: dump size, backup seconds, restore seconds, verify seconds, total RTO, table/row counts, date.

- [ ] **Step 2: Write `docs/runbooks/backup-restore.md`** — full structure below; replace every `«measured»` with the real drill numbers (leaving one in is a task failure):

```markdown
# Runbook: Postgres backup & restore

## What exists
- `scripts/backup/backup.sh` — `pg_dump -Fc` piped into `age` (encrypt-only,
  recipients file); local retention prunes files older than `RETENTION_DAYS`
  (default 30).
- `scripts/restore.sh` — decrypts the newest (or given) `.dump.age`, restores
  into a scratch DB (`agri_restore_drill`), and diffs exact per-table row
  counts against the source. Non-zero exit on any mismatch.
- `scripts/backup/wal-archive.sh` — WAL `archive_command` target for R2.
  **INACTIVE** until launch prep.

## Restore drill #1 — 2026-07-10, local Docker Postgres (agri-dev)
VPS is not provisioned yet (owner decision, docs/runbooks/staging-deploy.md);
drill #1 ran against the real dev database. Drill #2 re-runs this on the VPS
against a nightly dump during launch prep.

| measurement | value |
|---|---|
| dump size (age-encrypted) | «measured» |
| backup (pg_dump + encrypt) | «measured» s |
| restore (drop+create+decrypt+pg_restore) | «measured» s |
| verification (row-count diff) | «measured» s |
| **total RTO** | **«measured» s** |
| tables / rows verified | «measured» / «measured» |

Drill log excerpts:
```text
«paste the tail of /tmp/drill-backup.log and /tmp/drill-restore.log»
```

## Keys
- Dev drill keypair: `secrets/backup-age-key.txt` (identity) +
  `secrets/backup-age-recipients.txt` (public key). Both gitignored; dev-only.
- Production keypair: generated OFFLINE by the owner and stored offline;
  only the **recipient (public key)** goes to the VPS. Losing the identity
  file means backups are unrecoverable — that is the point of the drill.

## ACTIVATE AT LAUNCH PREP (owner-driven, in order)
1. Create the R2 bucket; apply the 30-day lifecycle rule:
   `{"Rules":[{"ID":"pg-30d","Status":"Enabled","Filter":{"Prefix":"pg/"},"Expiration":{"Days":30}},{"ID":"wal-30d","Status":"Enabled","Filter":{"Prefix":"wal/"},"Expiration":{"Days":30}}]}`
2. On the VPS: install `age` + `aws` CLI; place the production age recipient
   at `secrets/backup-age-recipients.txt`; export `BACKUP_UPLOAD_ENABLED=1`,
   `R2_BUCKET`, `R2_ENDPOINT` (account-specific), and R2 credentials for aws.
3. Nightly cron (VPS): `10 21 * * * cd ~/agri-ecosystem && PG_CONTAINER=agri-staging-postgres-1 bash scripts/backup/backup.sh >> ~/backup.log 2>&1`
   (21:10 UTC = 02:40 IST, low traffic).
4. Enable WAL archiving in the staging/prod postgres:
   `archive_mode=on`, `archive_command='.../wal-archive.sh %p %f'`.
5. Run RESTORE DRILL #2 on the VPS against last night's dump; update the
   timing table above with a second row.

## Failure playbook
- Backup script exits non-zero → nothing was pruned (prune runs last); rerun.
- Restore mismatch → the diff printed shows which tables diverge. A dump taken
  while migrations were running is the usual cause; take a fresh dump.
- Lost dev key → regenerate keypair, take a fresh backup; old local dumps are
  disposable. Production keys are the owner's offline responsibility.
```

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/backup-restore.md
git commit -m "docs(d05): restore drill #1 executed against local docker pg - measured RTO"
```

---

### Task 13: Uptime Kuma (ready-but-inactive) + monitoring runbook

**Files:**
- Create: `docker-compose.monitoring.yml`, `docs/runbooks/monitoring.md`
- Modify: `docs/runbooks/staging-deploy.md` (one cross-reference line)

- [ ] **Step 1: `docker-compose.monitoring.yml`:**

```yaml
# Uptime Kuma — READY BUT INACTIVE (D05). Do not start on the dev box; it
# runs on the VPS at launch prep. Bring-up + monitor list:
# docs/runbooks/monitoring.md
name: agri-monitoring

services:
  uptime-kuma:
    image: louislam/uptime-kuma:1
    ports:
      - "3011:3001"
    volumes:
      - kumadata:/app/data
    restart: unless-stopped

volumes:
  kumadata:
```

- [ ] **Step 2: `docs/runbooks/monitoring.md`:**

```markdown
# Runbook: monitoring & error tracking (READY BUT INACTIVE)

Everything here is wired but dormant. **ACTIVATE AT LAUNCH PREP** — nothing
below runs until the VPS exists (docs/runbooks/staging-deploy.md).

## Uptime Kuma
Bring-up (VPS): `docker compose -f docker-compose.monitoring.yml up -d`,
open :3011, create the admin account, then add monitors:

| monitor | type | interval | retries | notes |
|---|---|---|---|---|
| API /health | HTTP 200 | 60s | 1 | primary pager |
| API /health/deep | HTTP 200 | 300s | 3 | retries absorb dependency blips — alert-fatigue guard |
| each app / (5 URLs) | HTTP 200 keyword | 60s | 2 | staging ports 3100–3104, API 8100 |

Alert channel: email to r.aarun9597@gmail.com (SMTP notification with a Gmail
app password) + optional ntfy push to phone. Alert only on confirmed-down
(after retries) — no flapping notifications. Only these monitors: every alert
must be actionable (threat model: alert fatigue).

## Netdata (host metrics, VPS)
Install via the official kickstart script at launch prep. The API exposes
Prometheus-format app metrics at `GET /metrics` (p95 from the
http_request_duration_seconds histogram, error rate from
http_request_errors_total); Netdata's Prometheus collector scrapes it.
Swap path to a full Prometheus+Grafana stack: ADR-0011.

## Sentry
Code is fully wired, inactive without env:
- Backend: set `SENTRY_DSN` (+ optional `SENTRY_TRACES_SAMPLE_RATE`); release
  comes from `RELEASE` (git sha via docker build-arg).
- Apps: set `NEXT_PUBLIC_SENTRY_DSN` per app at deploy. Without it the client
  bundle contains zero sentry bytes (guard is inlined at build).
- Source maps: create the Sentry org + 6 projects (agri-api, agri-web-*), set
  repo secrets `SENTRY_AUTH_TOKEN` + `SENTRY_ORG`, and flip
  `"@sentry/cli": true` in pnpm-workspace.yaml allowBuilds.

## Activation checklist (launch prep, in order)
1. VPS up + staging deployed (docs/runbooks/staging-deploy.md).
2. Kuma up + monitors + email/ntfy channel; test one forced failure.
3. Netdata installed; confirm it scrapes /metrics.
4. Sentry DSNs in staging env; verify one thrown error arrives with the
   right release sha; then enable source-map upload (secrets + allowBuilds).
5. Backups: docs/runbooks/backup-restore.md activation section.
```

- [ ] **Step 3:** In `docs/runbooks/staging-deploy.md`, add one line to its post-deploy/next-steps area: `After first successful deploy, activate monitoring + backups: docs/runbooks/monitoring.md and docs/runbooks/backup-restore.md ("ACTIVATE AT LAUNCH PREP" sections).` (Read the file first and place it where it fits the flow.)

- [ ] **Step 4: Commit**

```bash
git add docker-compose.monitoring.yml docs/runbooks/monitoring.md docs/runbooks/staging-deploy.md
git commit -m "feat(d05): uptime kuma + monitoring runbook, ready-but-inactive"
```

---

### Task 14: ADRs — one per Constitution decision (+ observability stack)

**Files:**
- Create: `docs/adr/README.md` and `docs/adr/0001-…` through `docs/adr/0011-…` (list below)

Every ADR uses this exact skeleton and MUST state the reversal cost as a one-way/two-way door:

```markdown
# ADR-NNNN: <title>

**Status:** Accepted (2026-07-10) · **Reversal cost:** <one-way|two-way> door — <why>

## Context
<2-5 sentences>

## Decision
<2-5 sentences, referencing the enforcing code/gate>

## Consequences
<bullets: what we gain, what we give up, what would trigger revisiting>
```

`docs/adr/README.md` lists all 11 with one-line summaries and links, and carries the skeleton above as the template for future ADRs.

- [ ] **Step 1: Write the 11 ADRs.** File names and the content essentials (write each out in the skeleton; keep the stated door rating and enforcement pointers exactly):

1. **0001-modular-monolith.md** — One FastAPI deployable; modules under `backend/core/modules/*` isolated by import-linter independence contracts (pyproject.toml); cross-module talk via Redis Streams events or public service interfaces only. Chosen over microservices for a one-operator team. **Two-way door**: module boundaries + event bus mean any module can be extracted to a service later at moderate cost; the contracts exist precisely to keep this door open.
2. **0002-agriid-single-sso.md** — One identity (AgriID) across all five apps; `@agri/auth-client` is the only auth surface apps see; OAuth2 code + PKCE lands D06–D14. **One-way door in practice**: after launch, migrating user accounts/credentials to a different identity topology is a data migration with user-visible breakage; decided now, before any users exist, which is the cheap moment.
3. **0003-uuidv7-ids.md** — All IDs UUIDv7 (`uuid6` lib backend-side): time-ordered so b-tree index locality is good, globally unique so IDs can be minted anywhere. Enforced by convention + D03 mixins. **One-way door for existing rows** (rekeying data is prohibitive), two-way for new tables; treated as one-way.
4. **0004-cursor-pagination.md** — Every list endpoint is cursor-paginated (`shared/pagination.py`); OFFSET is banned by a test gate (D03). Stable under writes, O(1) at any depth. **Two-way door pre-launch, one-way after**: public API consumers bake in cursor contracts; changing later breaks clients.
5. **0005-jsonb-i18n.md** — Translatable content lives in JSONB columns (`{"en":…,"ta":…,"hi":…}`, `shared/i18n.py`) instead of translation tables: one row per entity, no fan-out joins, languages addable without migrations. **Two-way door**: a migration script can pivot JSONB into tables if per-language querying/indexing ever dominates.
6. **0006-slug-immutability.md** — Slugs never change; a rename records a redirect row and `SlugRedirectMiddleware` 301s old URLs (`shared/slugs.py`, `shared/middleware.py`). **One-way door**: SEO equity and shared links depend on it; "mutable slugs later" would orphan every published URL.
7. **0007-meilisearch.md** — Meilisearch v1.13 for search (typo tolerance, faceting, tiny ops footprint) over Elasticsearch (ops burden) and pg trigram (relevance ceiling). **Two-way door**: indexing goes through the search module only, so the engine can be swapped behind that interface; reindex is rebuildable from Postgres, the source of truth.
8. **0008-redis-streams-event-bus.md** — Cross-module communication via Redis Streams (`shared/events.py`): consumer groups (each module sees every event once), max 3 deliveries then `<stream>:dlq`. Chosen over Kafka/RabbitMQ (ops weight) and over synchronous calls (coupling). **Two-way door**: the publish/consume API is narrow; swapping the transport (e.g. to Postgres LISTEN/NOTIFY or Kafka) touches one shared module.
9. **0009-secure-router-default-private.md** — Every route is registered on `SecureRouter` (`shared/security.py`): 401 + rate-limited by default, `public=True` is the only bypass and is diffed against committed `public_routes.txt` in CI. Threat model: a future session forgetting auth. **One-way door as policy** (weakening it reopens the exact hole it closes), two-way per route.
10. **0010-lighthouse-ci-gate.md** — Public pages hold perf≥90/a11y≥95/seo≥95 (median of 3 runs) in CI (`lighthouserc.cjs`, D04); `/demo` carve-out perf≥80 is user-approved. **Two-way door mechanically, one-way as policy**: thresholds are config, but lowering them silently is the failure mode the gate exists to prevent — changes require an ADR update.
11. **0011-netdata-kuma-not-prometheus.md** — Observability stack is Netdata (host metrics, VPS) + Uptime Kuma (synthetic checks) + the app's own Prometheus-format `/metrics` — NOT a Prometheus+Grafana deployment (spec DO-NOT: right-sized for one operator). **Two-way door, deliberately**: `/metrics` already speaks Prometheus exposition format, so the swap path is "deploy Prometheus, point it at /metrics, add Grafana" with zero app changes. Revisit when >1 service or >1 operator.

- [ ] **Step 2: Verify coverage** — 11 files exist; `grep -L "door" docs/adr/0*.md` → empty (every ADR states the door).

- [ ] **Step 3: Commit**

```bash
git add docs/adr
git commit -m "docs(d05): 11 ADRs for constitution decisions with reversal costs"
```

---

### Task 15: Per-module CLAUDE.md files generated from a template

**Files:**
- Create: `backend/core/scripts/gen_module_claude.py`
- Create (generated): `backend/core/modules/<m>/CLAUDE.md` × 11

- [ ] **Step 1: Create the generator** `backend/core/scripts/gen_module_claude.py`:

```python
"""Generate modules/*/CLAUDE.md from one template (SPEC D05-H).

Edit MODULES / TEMPLATE here and rerun; never hand-edit the generated files.
Run from backend/core: python scripts/gen_module_claude.py
"""

from pathlib import Path

TEMPLATE = """\
<!-- GENERATED by scripts/gen_module_claude.py - edit the generator, not this file -->
# {name} module

{purpose}

**Spec pointer:** {spec}

## Boundary rules
- Never import from other modules (import-linter enforces independence);
  cross-module effects go through the Redis Streams event bus
  (shared/events.py) or the owning module's public service interface.
- Every route lives on a SecureRouter (shared/security.py); `public=True`
  requires updating backend/core/public_routes.txt in the same PR.
- IDs are UUIDv7; every list endpoint is cursor-paginated
  (shared/pagination.py) - OFFSET is banned by a test gate.
- User-generated content defaults to `pending` moderation state.

## Never do
- Never log request bodies or query strings - this module {pii_note}.
  PII scrubbing (shared/telemetry.py) is the last line of defence, not a licence.
- Never read another module's tables directly.
- Never bypass rate limiting or add an undeclared public route.
{extra_never}
"""

MODULES: dict[str, dict[str, str]] = {
    "identity": {
        "purpose": "AgriID SSO: users, sessions, OAuth2 code + PKCE, RBAC roles.",
        "spec": "Sprint 1, D06-D14 (docs/Execution schedule v5.MD - AgriID).",
        "pii_note": "handles auth and holds the most PII in the system",
        "extra_never": "- Never store plaintext credentials or tokens; "
        "never weaken require_auth outside specs D08-09.",
    },
    "coins": {
        "purpose": "AgriCoins ledger: balances, rewards, redemptions.",
        "spec": "Phase 1 plan - AgriCoins (docs/Execution schedule v5.MD).",
        "pii_note": "handles balance data tied to identities",
        "extra_never": "- Never mutate balances outside an append-only ledger "
        "entry; the flag `billing_enabled` gates real-money interplay.",
    },
    "directory": {
        "purpose": "Directory Engine E1: org/place profiles, branches, "
        "categories, verification, claims - the workhorse engine.",
        "spec": "docs/Execution schedule v5.MD SS E1 (~60% of verticals).",
        "pii_note": "holds business contact data (phones, emails)",
        "extra_never": "- Never render contact details without the "
        "lead/verification gate the vertical registry specifies.",
    },
    "leads": {
        "purpose": "Leads/intent matchmaking E4: buy/sell intents matched on "
        "category x geo x attributes.",
        "spec": "docs/Execution schedule v5.MD SS E4.",
        "pii_note": "carries buyer/seller contact intents (PII-dense)",
        "extra_never": "- Never reveal counterparty contacts before the "
        "verification gate; import/export leads are business-verified only.",
    },
    "content": {
        "purpose": "Content Engine E6: articles, news, guides, events - "
        "i18n'd and taggable by vertical + geo.",
        "spec": "docs/Execution schedule v5.MD SS E6.",
        "pii_note": "is mostly public content but comments/authorship attach to users",
        "extra_never": "- Never publish without the pending-by-default "
        "moderation flow; slugs are immutable (ADR-0006).",
    },
    "market_data": {
        "purpose": "Data/Info Engine E5: admin-managed structured datasets "
        "(mandi, schemes, helplines) rendered as reference sections.",
        "spec": "docs/Execution schedule v5.MD SS E5.",
        "pii_note": "should hold no personal data - datasets are public records",
        "extra_never": "- Never serve a dataset without source + as-of date "
        "metadata (data.gov.in sourcing traps: see memory d03-geo-data-sourcing).",
    },
    "ads": {
        "purpose": "Ads: flat-rate slot inventory targeted by vertical x geo "
        "x role x language, with admin approval.",
        "spec": "docs/Execution schedule v5.MD SS5 (Ads v2 at D85).",
        "pii_note": "handles advertiser billing contacts",
        "extra_never": "- Never serve an unlabeled ad ('Sponsored' always); "
        "the `ads_enabled` flag gates the whole module.",
    },
    "notify": {
        "purpose": "Notifications fan-out: in-app, email, SMS/WhatsApp later.",
        "spec": "docs/Execution schedule v5.MD - cross-cutting services.",
        "pii_note": "addresses messages to phones/emails by definition",
        "extra_never": "- Never log message bodies or destination "
        "addresses; log message ids and template ids only.",
    },
    "search": {
        "purpose": "Meilisearch indexing + query facade for all modules.",
        "spec": "docs/Execution schedule v5.MD - cross-cutting; ADR-0007.",
        "pii_note": "must not index private fields into public documents",
        "extra_never": "- Never index a field the owning module marks "
        "private; Postgres is the source of truth - indexes are rebuildable.",
    },
    "billing": {
        "purpose": "Razorpay payments: subscriptions, slot purchases, invoices.",
        "spec": "docs/Execution schedule v5.MD - monetisation stages.",
        "pii_note": "touches payment metadata (never store card/bank data)",
        "extra_never": "- Never handle raw card data (Razorpay hosted flows "
        "only); the `billing_enabled` flag is the master kill switch.",
    },
    "ai": {
        "purpose": "AI features: content generation at scale, assistants.",
        "spec": "docs/Execution schedule v5.MD SS4.3 (SEO page factory copy).",
        "pii_note": "must never send user PII to external model APIs",
        "extra_never": "- Never auto-publish generated copy without the "
        "human-spot-check flow; label AI-generated content as such.",
    },
}


def main() -> None:
    root = Path(__file__).resolve().parent.parent / "modules"
    for name, cfg in MODULES.items():
        target = root / name / "CLAUDE.md"
        target.write_text(TEMPLATE.format(name=name, **cfg), encoding="utf-8")
        print(f"wrote {target}")  # noqa: T201


if __name__ == "__main__":
    main()
```

(Note the `# noqa: T201` — ruff bans prints; script output is the point here. If the repo's other scripts handle this differently — check `scripts/load_geo.py` — copy their convention instead.)

- [ ] **Step 2: Run it** — `.venv/Scripts/python.exe scripts/gen_module_claude.py` (cwd `backend/core`) → 11 files written. Spot-read two for formatting.

- [ ] **Step 3: Gate** — `ruff format --check . && ruff check . && mypy .` → clean.

- [ ] **Step 4: Commit**

```bash
git add backend/core/scripts/gen_module_claude.py backend/core/modules/*/CLAUDE.md
git commit -m "docs(d05): per-module CLAUDE.md generated from template"
```

---

### Task 16: GATE 1 — evidence pack, full gates, PR, tag

**Files:**
- Create: `docs/runbooks/gate-1.md`

- [ ] **Step 1: Insecure-endpoint-fails-CI demo (local run of the exact CI gate).** Temporarily add to `backend/core/main.py` under the health routes:

```python
@health_router.get("/insecure-demo", public=True)
async def insecure_demo() -> HealthResponse:
    return HealthResponse(status="oops")
```

Run: `.venv/Scripts/python.exe scripts/dump_public_routes.py --check`
Expected: **non-zero exit** with a diff showing `/insecure-demo` undeclared — capture the output. Then revert: `git checkout backend/core/main.py`, rerun the check → exit 0.

- [ ] **Step 2: Fresh-clone timing drill (executed, timed).** In the session scratchpad:

```bash
cd <scratchpad> && date +%s > t0
git clone d:/agri-ecosystem agri-fresh && cd agri-fresh && git checkout feat/d05-observability
pnpm install
docker compose -f docker-compose.dev.yml up -d --build   # dev stack; postgres/redis/meili/minio + api
# poll until: docker compose -f docker-compose.dev.yml ps shows api healthy,
# then: curl -s http://localhost:8000/health  -> {"status":"ok"}
date +%s > t1
```
Compute minutes from t0→t1. Record honestly, including the caveat that docker base images were already in the local cache. Must be <15 min. Tear down with `docker compose -f docker-compose.dev.yml -p agri-fresh down` ONLY if a distinct project name was used — otherwise do NOT touch the running agri-dev project; the clone reuses the same compose project name, so **skip the up entirely if agri-dev is already running and instead time `pnpm install` + a `pnpm --filter @agri/web-agri build` as the stack-readiness proxy, and say so in the runbook**. Prefer stopping agri-dev first (`docker compose -f docker-compose.dev.yml down`) and running the true drill from the clone, then bringing agri-dev back up.

- [ ] **Step 3: Write `docs/runbooks/gate-1.md`:**

```markdown
# GATE 1 evidence (D05, 2026-07-10)

Definition of done: fresh clone -> running stack timed <15 min; an insecure
test endpoint fails CI; restore drill executed with real timings; v0.1.0.

## 1. Fresh clone -> running stack
«timing table: clone, pnpm install, docker compose up -> api healthy; total
minutes; caveats (image cache, which machine)»

## 2. Insecure endpoint fails CI
`scripts/dump_public_routes.py --check` — the same command CI's public-routes
job runs — with a temporary undeclared public route added:
```text
«captured non-zero output»
```

## 3. request-id trace (app -> API -> log)
/demo/trace on web-agri sent x-request-id «id»; the API JSON access line:
```text
«captured log line»
```

## 4. PII redaction sample
```text
«captured log line showing [REDACTED]»
```

## 5. Restore drill
Executed against local Docker Postgres — measured RTO in
docs/runbooks/backup-restore.md.

## Known gaps carried into Sprint 1
- Branch protection is convention-only on the free plan
  (docs/runbooks/branch-protection.md) — revisited here per D04, still owner's
  call; enforcement activates on Team upgrade.
- Kuma/R2/Sentry/WAL are ready-but-inactive until the VPS exists
  (docs/runbooks/monitoring.md, backup-restore.md).
```

Fill every «» with real captured output from Steps 1–2 and Task 9/12 evidence.

- [ ] **Step 4: Full gates, both stacks** (from repo root and `backend/core`):

```bash
cd backend/core && ruff format --check . && ruff check . && mypy . && lint-imports && .venv/Scripts/python.exe scripts/migrate_check.py && .venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe scripts/dump_public_routes.py --check
cd ../.. && node scripts/check-hex.mjs && pnpm exec turbo run lint typecheck test build
```
Expected: everything green. Fix anything red before the PR — never open a red PR.

- [ ] **Step 5: Commit gate doc, push, open PR** (REST API via `git credential fill` — no gh CLI; same recipe as PR #3):

```bash
git add docs/runbooks/gate-1.md
git commit -m "docs(d05): gate 1 evidence - clone timing, insecure-endpoint demo, traces"
git push -u origin feat/d05-observability
```
PR: title `feat(d05): observability, backups + restore drill, gate 1`, base `dev`. Body: summary of A–H with the no-VPS adaptations called out (drill ran locally; Kuma/R2/Sentry inactive), links to the three runbooks, measured RTO, and the trace/PII evidence.

- [ ] **Step 6: After the PR is green and merged into dev** (owner merges per convention; do not merge a red PR, never push dev):

```bash
git fetch origin dev
git tag -a v0.1.0 -m "Gate 1: observability + backups + restore drill #1" origin/dev
git push origin v0.1.0
```

- [ ] **Step 7:** Update auto-memory: write `d05-observability-decisions.md` (new traps/decisions discovered during execution) and add its line to MEMORY.md.

---

## Self-Review (performed)

- **Spec coverage:** A→Tasks 5–8 (Sentry BE+FE+sourcemaps CI); B→1, 2, 9 (JSON logs, PII test, request-id FE→BE demo, env-driven levels via existing `log_level`); C→3, 4 (pg_stat_statements, 200ms slow-query log, p95 histogram + error counters, /metrics); D→13 (Kuma ready-inactive per owner's no-VPS directive); E→10, 11 (pg_dump+age, WAL/R2 inactive, 30-day retention local + lifecycle doc); F→12 (drill executed locally — user-directed adaptation); G→14 (11 ADRs incl. the DO-NOT's swap-path note in 0011); H→15; DoD→16 (timed clone, insecure endpoint, tag v0.1.0).
- **Non-negotiables:** PII test green (Task 1); drill executed+timed+documented (12); every ADR states the door (14 Step 2 grep); request-id demo (9→16).
- **Placeholder scan:** the only «» fields are drill-time measurements/captures, explicitly required to be filled with real output; `<pnpm-pinned>` versions are resolved by `pnpm add` at execution.
- **Type consistency:** `observe_request(method, route, status, seconds)` stub (Task 2) matches the real one (Task 3); `REQUEST_ID_HEADER` value `x-request-id` identical in `request_context.py` and `api.ts`; env names (`PG_CONTAINER`, `AGE_KEY_FILE`, `R2_BUCKET`, `R2_ENDPOINT`, `BACKUP_UPLOAD_ENABLED`) match across backup.sh/restore.sh/wal-archive.sh/runbooks.
