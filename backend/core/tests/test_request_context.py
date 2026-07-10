"""Request-id propagation, response header, JSON access log line."""

import json
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from main import create_app
from shared.request_context import REQUEST_ID_HEADER
from shared.telemetry import JsonFormatter, PiiScrubFilter


def client() -> TestClient:
    return TestClient(create_app())


def test_response_carries_generated_request_id() -> None:
    response = client().get("/health")
    rid = response.headers.get(REQUEST_ID_HEADER)
    assert rid is not None and len(rid) == 36  # uuid7 string


def test_inbound_request_id_is_echoed() -> None:
    response = client().get("/health", headers={REQUEST_ID_HEADER: "trace-me-12345"})
    assert response.headers[REQUEST_ID_HEADER] == "trace-me-12345"


def test_invalid_inbound_id_is_replaced() -> None:
    hostile = "abc def<script>"
    response = client().get("/health", headers={REQUEST_ID_HEADER: hostile})
    assert response.headers[REQUEST_ID_HEADER] != hostile


def test_access_log_line_is_json_with_request_id(caplog: pytest.LogCaptureFixture) -> None:
    handler_filter = PiiScrubFilter()
    with caplog.at_level(logging.INFO, logger="agri.access"):
        client().get("/health", headers={REQUEST_ID_HEADER: "trace-me-12345"})
    record = next(r for r in caplog.records if r.name == "agri.access")
    handler_filter.filter(record)
    payload: dict[str, Any] = json.loads(JsonFormatter().format(record))
    assert payload["request_id"] == "trace-me-12345"
    assert payload["method"] == "GET"
    assert payload["path"] == "/health"
    assert payload["route"] == "/health"
    assert payload["status"] == 200
    assert payload["duration_ms"] >= 0
    assert "?" not in payload["path"]
