from __future__ import annotations

import io
import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from photos_sync.observability import (
    EVENT_LOGGER,
    HTTP_REQUESTS,
    JsonFormatter,
    ObservabilityMiddleware,
)


def test_request_uses_route_template_and_propagates_request_id() -> None:
    app = FastAPI()
    app.add_middleware(ObservabilityMiddleware)

    @app.get("/items/{item_id}")
    def item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    metric = HTTP_REQUESTS.labels(method="GET", route="/items/{item_id}", status="200")
    before = metric._value.get()

    response = TestClient(app).get(
        "/items/private-value", headers={"X-Request-ID": "browser-request-42"}
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "browser-request-42"
    assert metric._value.get() == before + 1


def test_access_log_does_not_include_query_string() -> None:
    app = FastAPI()
    app.add_middleware(ObservabilityMiddleware)

    @app.get("/search")
    def search() -> dict[str, bool]:
        return {"ok": True}

    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonFormatter())
    EVENT_LOGGER.addHandler(handler)
    try:
        response = TestClient(app).get("/search?token=do-not-log-this")
    finally:
        EVENT_LOGGER.removeHandler(handler)

    assert response.status_code == 200
    assert "do-not-log-this" not in output.getvalue()
    event = json.loads(output.getvalue().strip())
    assert event["event"] == "http_request"
    assert event["route"] == "/search"
    assert event["path"] == "/search"
    assert event["status"] == 200


def test_invalid_request_id_is_replaced() -> None:
    app = FastAPI()
    app.add_middleware(ObservabilityMiddleware)

    @app.get("/")
    def root() -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(app).get("/", headers={"X-Request-ID": "invalid id with spaces"})

    assert response.headers["x-request-id"].startswith("req_")
    assert " " not in response.headers["x-request-id"]
