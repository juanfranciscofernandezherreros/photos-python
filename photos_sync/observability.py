"""Application metrics and structured logging."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from prometheus_client import Counter, Gauge, Histogram, start_http_server

SERVICE_NAME = os.getenv("SERVICE_NAME", "mi-api")

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "HTTP requests handled by the application.",
    ("service", "route", "method", "status_code"),
)
HTTP_REQUEST_DURATION = Histogram(
    "photos_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "photos_http_requests_in_progress",
    "HTTP requests currently being handled.",
    ("method",),
)
HTTP_RESPONSE_SIZE = Counter(
    "photos_http_response_size_bytes_total",
    "Total HTTP response body bytes sent.",
    ("method", "route"),
)
HTTP_EXCEPTIONS = Counter(
    "photos_http_exceptions_total",
    "Unhandled exceptions raised while serving HTTP requests.",
    ("method", "route", "exception_type"),
)

WEBSOCKET_CONNECTIONS = Gauge(
    "photos_websocket_connections_active",
    "Currently active WebSocket connections.",
    ("route",),
)
WEBSOCKET_CONNECTIONS_TOTAL = Counter(
    "photos_websocket_connections_total",
    "WebSocket connections accepted.",
    ("route",),
)

PIPELINE_RUNNING = Gauge(
    "photos_pipeline_running",
    "Whether the synchronization pipeline is currently running.",
)
PIPELINE_RUNS = Counter(
    "photos_pipeline_runs_total",
    "Synchronization pipeline executions.",
    ("status",),
)
PIPELINE_DURATION = Histogram(
    "photos_pipeline_duration_seconds",
    "Synchronization pipeline execution duration.",
    ("status",),
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800, 3600),
)
PIPELINE_STEP_DURATION = Histogram(
    "photos_pipeline_step_duration_seconds",
    "Synchronization pipeline step duration.",
    ("step", "status"),
    buckets=(0.1, 0.5, 1, 2.5, 5, 15, 30, 60, 120, 300, 900),
)
PIPELINE_LAST_RUN_SUCCESS = Gauge(
    "photos_pipeline_last_run_success",
    "Whether the last completed pipeline execution succeeded (1 or 0).",
)
PIPELINE_LAST_RUN_TIMESTAMP = Gauge(
    "photos_pipeline_last_run_timestamp_seconds",
    "Unix timestamp of the last completed pipeline execution.",
)

WEBDAV_JOBS_RUNNING = Gauge(
    "photos_webdav_jobs_running",
    "WebDAV downloads currently running.",
)
WEBDAV_JOBS = Counter(
    "photos_webdav_jobs_total",
    "WebDAV download jobs.",
    ("status",),
)
WEBDAV_JOB_DURATION = Histogram(
    "photos_webdav_job_duration_seconds",
    "WebDAV download job duration.",
    ("status",),
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800, 3600),
)
WEBDAV_PHOTOS = Counter(
    "photos_webdav_photos_total",
    "Photos handled by WebDAV download jobs.",
    ("outcome",),
)
WEBDAV_LAST_JOB_SUCCESS = Gauge(
    "photos_webdav_last_job_success",
    "Whether the last completed WebDAV job succeeded (1 or 0).",
)
WEBDAV_LAST_JOB_TIMESTAMP = Gauge(
    "photos_webdav_last_job_timestamp_seconds",
    "Unix timestamp of the last completed WebDAV job.",
)
WEBDAV_WORKERS_CONFIGURED = Gauge(
    "photos_webdav_workers_configured",
    "Configured WebDAV transfer worker count.",
)
WEBDAV_FILES_TOTAL = Gauge(
    "photos_webdav_files_discovered",
    "Files discovered by the current WebDAV job.",
)
WEBDAV_FILES_QUEUED = Gauge(
    "photos_webdav_files_queued",
    "WebDAV files waiting for a transfer worker.",
)
WEBDAV_ACTIVE_TRANSFERS = Gauge(
    "photos_webdav_transfers_active",
    "WebDAV file transfers currently active.",
)
WEBDAV_FILES_COMPLETED = Gauge(
    "photos_webdav_files_completed",
    "Files completed by the current WebDAV job.",
)
WEBDAV_FILES_FAILED = Gauge(
    "photos_webdav_files_failed",
    "Files failed in the current WebDAV job.",
)
WEBDAV_BYTES_RECEIVED = Counter(
    "photos_webdav_received_bytes_total",
    "Bytes received from WebDAV servers, including retried transfer data.",
)
WEBDAV_RESUMED_TRANSFERS = Counter(
    "photos_webdav_resumed_transfers_total",
    "WebDAV transfers resumed with HTTP Range.",
)


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SENSITIVE_RESPONSE_KEYS = {
    "access_token", "api_key", "authorization", "cookie", "password", "passwd",
    "refresh_token", "secret", "set_cookie", "token",
}
_STANDARD_LOG_FIELDS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName",
}


class JsonFormatter(logging.Formatter):
    """Emit one compact JSON object per line for Loki ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "event": getattr(record, "event", "application_log"),
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_FIELDS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("photos_sync.events")
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger


EVENT_LOGGER = _build_logger()


def log_event(event: str, *, level: str = "info", message: str | None = None, **fields: Any) -> None:
    """Write a structured event without serializing request headers."""

    log_method = getattr(EVENT_LOGGER, level.lower(), EVENT_LOGGER.info)
    log_method(message or event, extra={"event": event, **fields})


def _env_enabled(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def start_metrics_endpoint() -> tuple[Any, threading.Thread] | None:
    """Start the dedicated internal Prometheus endpoint."""

    if not _env_enabled("METRICS_ENABLED", not _env_enabled("TESTING", False)):
        return None
    address = os.getenv("METRICS_ADDR", "127.0.0.1")
    port = int(os.getenv("METRICS_PORT", "9000"))
    result = start_http_server(port, addr=address)
    log_event("metrics_server_started", address=address, port=port)
    return result


def stop_metrics_endpoint(handles: tuple[Any, threading.Thread] | None) -> None:
    if handles is None:
        return
    server, thread = handles
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    log_event("metrics_server_stopped")


def _correlation_id(headers: Iterable[tuple[bytes, bytes]]) -> str:
    decoded = {name.lower(): value for name, value in headers}
    for header in (b"x-correlation-id", b"x-request-id"):
        if header in decoded:
            candidate = decoded[header].decode("ascii", errors="ignore")
            if _REQUEST_ID_RE.fullmatch(candidate):
                return candidate
    return f"req_{uuid.uuid4().hex}"


def _route_template(scope: dict[str, Any]) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) and path else "unmatched"


def _redact_response(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if str(key).lower() in _SENSITIVE_RESPONSE_KEYS else _redact_response(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_response(item) for item in value]
    return value


def _response_body_for_log(content_type: str, body: bytes) -> str | None:
    normalized_type = content_type.partition(";")[0].strip().lower()
    is_json = normalized_type == "application/json" or normalized_type.endswith("+json")
    is_text = normalized_type.startswith("text/")
    if not body or not (is_json or is_text):
        return None

    text = body.decode("utf-8", errors="replace")
    if not is_json:
        return text
    try:
        return json.dumps(
            _redact_response(json.loads(text)),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except json.JSONDecodeError:
        return text


class ObservabilityMiddleware:
    """Low-overhead ASGI request metrics and access logs."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "UNKNOWN")).upper()
        correlation_id = _correlation_id(scope.get("headers", ()))
        started = time.perf_counter()
        status = 500
        response_size = 0
        response_content_type = ""
        response_body = bytearray()
        response_log_limit = max(0, int(os.getenv("LOG_RESPONSE_MAX_BYTES", "16384")))
        response_body_truncated = False
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()

        client = scope.get("client")
        client_ip = client[0] if client else None
        log_event(
            "http_request_received",
            message="HTTP request received",
            service=SERVICE_NAME,
            correlation_id=correlation_id,
            method=method,
            route=str(scope.get("path", "")),
            path=str(scope.get("path", "")),
            client_ip=client_ip,
        )

        async def observed_send(message: dict[str, Any]) -> None:
            nonlocal status, response_size, response_content_type, response_body_truncated
            if message["type"] == "http.response.start":
                status = int(message["status"])
                headers = list(message.get("headers", ()))
                for name, value in headers:
                    if name.lower() == b"content-type":
                        response_content_type = value.decode("latin-1", errors="replace")
                        break
                headers.append((b"x-request-id", correlation_id.encode("ascii")))
                headers.append((b"x-correlation-id", correlation_id.encode("ascii")))
                message["headers"] = headers
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                response_size += len(chunk)
                remaining = response_log_limit - len(response_body)
                if remaining > 0:
                    response_body.extend(chunk[:remaining])
                if len(chunk) > max(remaining, 0):
                    response_body_truncated = True
            await send(message)

        exception: BaseException | None = None
        try:
            await self.app(scope, receive, observed_send)
        except BaseException as exc:
            exception = exc
            raise
        finally:
            duration = time.perf_counter() - started
            route = _route_template(scope)
            status_text = str(status)
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()
            HTTP_REQUESTS.labels(
                service=SERVICE_NAME,
                route=route,
                method=method,
                status_code=status_text,
            ).inc()
            HTTP_REQUEST_DURATION.labels(method=method, route=route).observe(duration)
            HTTP_RESPONSE_SIZE.labels(method=method, route=route).inc(response_size)
            if exception is not None:
                HTTP_EXCEPTIONS.labels(
                    method=method,
                    route=route,
                    exception_type=type(exception).__name__,
                ).inc()

            level = "error" if status >= 500 else "warning" if status >= 400 else "info"
            log_event(
                "http_response",
                level=level,
                message="HTTP request completed",
                service=SERVICE_NAME,
                correlation_id=correlation_id,
                method=method,
                route=route,
                path=str(scope.get("path", "")),
                status_code=status,
                status_class=f"{status // 100}xx",
                duration_ms=round(duration * 1000, 3),
                response_size=response_size,
                response_content_type=response_content_type,
                response_body=_response_body_for_log(response_content_type, bytes(response_body)),
                response_body_truncated=response_body_truncated,
                client_ip=client_ip,
                exception_type=type(exception).__name__ if exception else None,
            )


def configure_observability(app: Any) -> None:
    app.add_middleware(ObservabilityMiddleware)
