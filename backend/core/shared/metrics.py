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

# OTP abuse telemetry (D07): aggregates only. Phones and IPs must never become
# label values (unbounded cardinality + PII); per-phone/per-IP counting lives
# in the Redis throttle keys (modules/identity/otp_throttle.py).
OTP_ISSUED = Counter(
    "otp_issued_total",
    "OTP codes issued",
    ["purpose", "driver"],
    registry=registry,
)
OTP_VERIFIED = Counter(
    "otp_verify_total",
    "OTP verification attempts by outcome",
    ["result"],
    registry=registry,
)
OTP_SEND_COST = Counter(
    "otp_send_cost_inr_total",
    "Cumulative SMS send cost in INR (vendor drivers only)",
    ["provider"],
    registry=registry,
)

# Coins nightly balance-integrity check (D13): incremented once per user found
# to have drifted between the stored materialized balance and the recomputed
# ledger sum. No labels - user_id must never become a label value.
COINS_BALANCE_DRIFT = Counter(
    "coins_balance_drift_total",
    "users whose stored balance drifted from the recomputed ledger sum",
    registry=registry,
)

# Audit chain telemetry (D12): counts only - entry contents never label metrics.
AUDIT_CHAIN_DAYS_VERIFIED = Counter(
    "audit_chain_days_verified_total",
    "Audit chain day-verifications by outcome",
    ["result"],  # ok | broken
    registry=registry,
)
AUDIT_CHAIN_BREAKS = Counter(
    "audit_chain_breaks_total",
    "Individual audit chain breaks detected",
    # unlabeled Counters have no working .clear() (D07 trap); "reason" is
    # bounded to hash_mismatch|link_mismatch|seq_gap so cardinality is safe.
    ["reason"],
    registry=registry,
)

NOTIFY_SENT = Counter(
    "notify_sends_total",
    "Notification channel outcomes",
    ["channel", "status"],  # status: sent | failed | dead
    registry=registry,
)
NOTIFY_DROPPED = Counter(
    "notify_dropped_total",
    "Notifications or channel sends suppressed before any driver call",
    ["reason"],  # rate_cap | preference | flag | no_destination
    registry=registry,
)

# Billing webhook rejections (D20): forgery/replay telemetry. Reasons are a
# small fixed set - never ids or payload fragments.
BILLING_WEBHOOK_REJECTED = Counter(
    "billing_webhook_rejected_total",
    "Razorpay webhooks rejected before processing",
    ["reason"],
    registry=registry,
)
BILLING_RECONCILE_MISMATCH = Counter(
    "billing_reconcile_mismatch_total",
    "Local vs Razorpay state mismatches found by the nightly reconciliation",
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
    for metric in (
        REQUESTS,
        ERRORS,
        LATENCY,
        OTP_ISSUED,
        OTP_VERIFIED,
        OTP_SEND_COST,
        AUDIT_CHAIN_DAYS_VERIFIED,
        AUDIT_CHAIN_BREAKS,
        NOTIFY_SENT,
        NOTIFY_DROPPED,
        BILLING_WEBHOOK_REJECTED,
        # BILLING_RECONCILE_MISMATCH intentionally excluded: unlabeled Counters
        # have no working .clear() (D07 trap, same reason COINS_BALANCE_DRIFT
        # above is excluded) - AttributeError: 'Counter' object has no
        # attribute '_lock'.
    ):
        metric.clear()
