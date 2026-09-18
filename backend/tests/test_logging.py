"""Logging / client ingest tests."""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import reset_db_state
from app.dependencies import Services
from app.logging import JsonFormatter, configure_logging, record_to_ecs, shutdown_logging
from app.main import create_app
from test_api import FakeAlpaca, FakeFinnhub, FakeKronos, FakeSec


def _test_settings(**overrides) -> Settings:
    defaults = dict(
        _env_file=None,
        database_url="sqlite://",
        app_environment="test",
        api_key=None,
        prediction_enabled=False,
        sec_enabled=False,
        agent_scheduler_enabled=False,
        elasticsearch_enabled=False,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _client(settings: Settings | None = None) -> TestClient:
    reset_db_state()
    settings = settings or _test_settings()
    services = Services(settings, FakeAlpaca(), FakeFinnhub(), FakeKronos(), FakeSec(), prediction=None, trading_agent=None)
    return TestClient(create_app(settings, services))


def test_json_formatter_includes_ecs_fields():
    configure_logging(level="INFO", environment="test", elasticsearch_enabled=False)
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.request_id = "abc-123"  # type: ignore[attr-defined]
    record.method = "GET"  # type: ignore[attr-defined]
    record.path = "/api/v1/health"  # type: ignore[attr-defined]
    record.status_code = 200  # type: ignore[attr-defined]
    record.duration_ms = 12.5  # type: ignore[attr-defined]
    payload = record_to_ecs(record)
    assert payload["@timestamp"]
    assert payload["log.level"] == "INFO"
    assert payload["service.name"] == "stockpulse"
    assert payload["trace.id"] == "abc-123"
    assert payload["http.request.method"] == "GET"
    assert payload["url.path"] == "/api/v1/health"
    assert payload["http.response.status_code"] == 200
    text = JsonFormatter().format(record)
    parsed = json.loads(text)
    assert parsed["message"] == "hello"
    shutdown_logging()


def test_app_starts_with_elasticsearch_disabled():
    with _client(_test_settings(elasticsearch_enabled=False, elasticsearch_url=None)) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
    shutdown_logging()


def test_client_logs_endpoint_accepts_batch():
    with _client() as client:
        resp = client.post(
            "/api/v1/logs/client",
            json={
                "events": [
                    {
                        "level": "error",
                        "message": "ui_boom",
                        "context": {"panel": "trading-agent"},
                        "stack": "Error: boom",
                        "path": "/trading-agent",
                    }
                ]
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["accepted"] == 1
    shutdown_logging()


def test_client_logs_rejects_empty_batch():
    with _client() as client:
        resp = client.post("/api/v1/logs/client", json={"events": []})
        assert resp.status_code == 422
    shutdown_logging()


def test_client_logs_rejects_invalid_level():
    with _client() as client:
        resp = client.post(
            "/api/v1/logs/client",
            json={"events": [{"level": "fatal", "message": "nope"}]},
        )
        assert resp.status_code == 422
    shutdown_logging()


def test_client_logs_rate_limited():
    with _client() as client:
        payload = {"events": [{"level": "info", "message": "ping"}]}
        last = None
        for _ in range(121):
            last = client.post("/api/v1/logs/client", json=payload)
        assert last is not None
        assert last.status_code == 429
        assert last.headers.get("Retry-After") == "60"
    shutdown_logging()
