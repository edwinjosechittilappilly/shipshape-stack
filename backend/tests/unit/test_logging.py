import json
import logging
import sys

import pytest
from fastapi.testclient import TestClient

from app.log_config import JsonFormatter


def test_formatter_emits_one_json_object_with_extras() -> None:
    record = logging.LogRecord(
        "app.test", logging.WARNING, __file__, 1, "hello %s", ("world",), None
    )
    record.request_path = "/x"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "hello world"
    assert (payload["level"], payload["logger"], payload["request_path"]) == (
        "WARNING",
        "app.test",
        "/x",
    )
    assert payload["timestamp"].endswith("+00:00")


def test_formatter_includes_exception_traceback() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    assert "ValueError: boom" in json.loads(JsonFormatter().format(record))["exception"]


def test_requests_are_logged_with_structured_fields(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.access"):
        client.get("/api/v1/items")
    record = next(r for r in caplog.records if r.name == "app.access")
    payload = json.loads(JsonFormatter().format(record))
    assert (payload["method"], payload["path"], payload["status"]) == ("GET", "/api/v1/items", 200)
    assert payload["duration_ms"] >= 0


def test_probe_requests_are_not_logged_at_info(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.access"):
        client.get("/healthz")
    assert not [r for r in caplog.records if r.name == "app.access"]
