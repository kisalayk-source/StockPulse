"""JSON / ECS-oriented logging with optional Elasticsearch bulk shipping."""

from __future__ import annotations

import json
import logging
import queue
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


_STANDARD_FIELDS = set(logging.makeLogRecord({}).__dict__)
_SERVICE_NAME = "stockpulse"
_shipper: "ElasticsearchLogShipper | None" = None


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per line (stdout + Elastic ingest friendly)."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(record_to_ecs(record, self), default=str, separators=(",", ":"))


def record_to_ecs(record: logging.LogRecord, formatter: logging.Formatter | None = None) -> dict[str, Any]:
    """Map a LogRecord to ECS-ish fields while keeping legacy aliases."""
    fmt = formatter or logging.Formatter()
    now = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "@timestamp": now,
        "timestamp": now,  # legacy alias used by existing tooling
        "log.level": record.levelname,
        "level": record.levelname,
        "log.logger": record.name,
        "logger": record.name,
        "message": record.getMessage(),
        "service.name": _SERVICE_NAME,
        "service.environment": getattr(record, "service_environment", None)
        or getattr(record, "environment", None),
    }
    # Drop null environment until settings inject it
    if not payload["service.environment"]:
        payload.pop("service.environment", None)

    for key, value in record.__dict__.items():
        if key in _STANDARD_FIELDS or key in {"message", "asctime"}:
            continue
        if key in {"service_environment", "environment"}:
            continue
        payload[key] = value

    # Common ECS renames when callers still pass Kronos-style extras
    if "request_id" in payload and "trace.id" not in payload:
        payload["trace.id"] = payload["request_id"]
    if "method" in payload and "http.request.method" not in payload:
        payload["http.request.method"] = payload["method"]
    if "path" in payload and "url.path" not in payload:
        payload["url.path"] = payload["path"]
    if "status_code" in payload and "http.response.status_code" not in payload:
        payload["http.response.status_code"] = payload["status_code"]
    if "duration_ms" in payload and "event.duration" not in payload:
        try:
            payload["event.duration"] = int(float(payload["duration_ms"]) * 1_000_000)
        except (TypeError, ValueError):
            pass

    if record.exc_info:
        payload["error.stack_trace"] = fmt.formatException(record.exc_info)
        payload["exception"] = payload["error.stack_trace"]
        if record.exc_info[0] is not None:
            payload["error.type"] = getattr(record.exc_info[0], "__name__", str(record.exc_info[0]))
    return payload


class ElasticsearchLogShipper:
    """Background bulk indexer for free/local Elasticsearch (no security)."""

    def __init__(
        self,
        url: str,
        *,
        index: str = "stockpulse-logs",
        flush_seconds: float = 2.0,
        max_batch: int = 50,
    ) -> None:
        self._url = url.rstrip("/")
        self._index = index
        self._flush_seconds = max(0.5, float(flush_seconds))
        self._max_batch = max(1, int(max_batch))
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=2000)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="elastic-log-shipper", daemon=True)
        self._thread.start()

    def emit(self, document: dict[str, Any]) -> None:
        if self._stop.is_set():
            return
        try:
            self._queue.put_nowait(document)
        except queue.Full:
            pass

    def close(self) -> None:
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join(timeout=5.0)

    def _run(self) -> None:
        batch: list[dict[str, Any]] = []
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=self._flush_seconds)
            except queue.Empty:
                item = None
                if batch:
                    self._flush(batch)
                    batch = []
                continue
            if item is None:
                break
            batch.append(item)
            if len(batch) >= self._max_batch:
                self._flush(batch)
                batch = []
        if batch:
            self._flush(batch)

    def _flush(self, batch: list[dict[str, Any]]) -> None:
        lines: list[str] = []
        for doc in batch:
            lines.append(json.dumps({"index": {"_index": self._index}}, separators=(",", ":")))
            lines.append(json.dumps(doc, default=str, separators=(",", ":")))
        body = ("\n".join(lines) + "\n").encode("utf-8")
        req = urllib.request.Request(
            f"{self._url}/_bulk",
            data=body,
            headers={"Content-Type": "application/x-ndjson"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except (urllib.error.URLError, TimeoutError, OSError):
            # Never crash the app because logging backend is down.
            pass


class ElasticsearchHandler(logging.Handler):
    def __init__(self, shipper: ElasticsearchLogShipper) -> None:
        super().__init__()
        self._shipper = shipper

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._shipper.emit(record_to_ecs(record))
        except Exception:
            self.handleError(record)


_factory_installed = False


def configure_logging(
    *,
    level: str = "INFO",
    environment: str = "production",
    elasticsearch_url: str | None = None,
    elasticsearch_index: str = "stockpulse-logs",
    elasticsearch_enabled: bool = False,
) -> None:
    global _shipper, _factory_installed

    root = logging.getLogger()
    app_logger = logging.getLogger("app")

    # Avoid duplicate handlers on reload
    if any(getattr(handler, "_kronos_json", False) for handler in app_logger.handlers):
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler._kronos_json = True  # type: ignore[attr-defined]
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not _factory_installed:
        old_factory = logging.getLogRecordFactory()

        def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = old_factory(*args, **kwargs)
            if not hasattr(record, "service_environment"):
                record.service_environment = environment  # type: ignore[attr-defined]
            return record

        logging.setLogRecordFactory(record_factory)
        _factory_installed = True

    log_level = getattr(logging, level.upper(), logging.INFO)
    for name in ("app", "uvicorn", "uvicorn.error", "uvicorn.access", "ml", "forecasting"):
        named = logging.getLogger(name)
        named.handlers.clear()
        named.addHandler(handler)
        named.setLevel(log_level)
        named.propagate = False

    # Also attach to root so third-party modules get JSON when they propagate
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    if elasticsearch_enabled and elasticsearch_url:
        _shipper = ElasticsearchLogShipper(elasticsearch_url, index=elasticsearch_index)
        es_handler = ElasticsearchHandler(_shipper)
        es_handler.setLevel(log_level)
        es_handler._kronos_json = True  # type: ignore[attr-defined]
        for name in ("app", "uvicorn", "uvicorn.error", "ml", "forecasting"):
            logging.getLogger(name).addHandler(es_handler)
        root.addHandler(es_handler)
        logging.getLogger("app").info(
            "elasticsearch_logging_enabled",
            extra={"elasticsearch_url": elasticsearch_url, "elasticsearch_index": elasticsearch_index},
        )


def shutdown_logging() -> None:
    global _shipper
    if _shipper is not None:
        _shipper.close()
        _shipper = None


def get_shipper() -> ElasticsearchLogShipper | None:
    return _shipper
