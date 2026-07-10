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
                    # request_id is repeated here so the access record stays
                    # self-contained even when formatted after the contextvar
                    # is reset (deferred/async handlers)
                    "extra_fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "route": route_path,
                        "status": status,
                        "duration_ms": round(duration_ms, 1),
                        "request_id": request_id,
                    }
                },
            )
            request_id_var.reset(token)
