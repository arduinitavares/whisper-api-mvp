"""
Contract tests for a unified error envelope returned by the API.

These tests codify the desired RapidAPI-friendly error shape:

    {
        "error": str,         # generic status phrase (e.g., "Unsupported Media Type")
        "code": int,          # HTTP status code
        "details": Optional[str | list]  # human-readable detail or a list of validation issues
    }

They are intentionally written first (TDD) and will FAIL until the app
installs global exception handlers that:
- Map FastAPI/Starlette HTTPException -> envelope (using status phrase as `error`).
- Map validation errors to **400** with `details` as a non-empty list.
- Map unexpected exceptions to **500** with a generic message and no internals leaked.

No external I/O is performed; we add temporary routes only for testing
and remove them after each test to keep the global app clean.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app


@contextmanager
def temp_route(path: str, *, method: str = "GET", handler):
    """Register a temporary route on the shared app and remove it afterwards."""
    app.add_api_route(path, handler, methods=[method])
    try:
        yield
    finally:
        # remove the last route we just added (FastAPI keeps them in order)
        if app.router.routes:
            app.router.routes.pop()


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# 1) HTTPException -> envelope
# ---------------------------------------------------------------------------


def test_http_exception_uses_unified_envelope(client: TestClient) -> None:
    """Raising HTTPException in a route returns the unified error envelope."""

    async def boom():  # pragma: no cover - exercised via client
        raise HTTPException(status_code=415, detail="Unsupported file type: .txt")

    with temp_route("/_raise_http", method="GET", handler=boom):
        resp = client.get("/_raise_http")

    assert resp.status_code == 415
    data = resp.json()

    # contract shape
    assert set(data.keys()) == {"error", "code", "details"}
    assert data["code"] == 415
    # generic phrase, not our internal text
    assert data["error"] == "Unsupported Media Type"
    # human detail is preserved (but not under `detail`)
    assert (
        isinstance(data["details"], str) and "Unsupported file type" in data["details"]
    )
    assert "detail" not in data


# ---------------------------------------------------------------------------
# 2) Validation error -> 400 with details array
# ---------------------------------------------------------------------------


def test_validation_errors_are_400_with_details_array(
    auth_test_client: TestClient, auth_headers
) -> None:
    """Missing/invalid fields in request return 400 with details as a non-empty list."""
    # Missing form field -> should be 400
    resp = auth_test_client.post("/v1/transcribe", files={}, headers=auth_headers)

    assert resp.status_code == 400
    data = resp.json()

    assert set(data.keys()) == {"error", "code", "details"}
    assert data["error"] == "Bad Request"
    assert data["code"] == 400
    assert isinstance(data["details"], list) and len(data["details"]) > 0
    assert "detail" not in data


# ---------------------------------------------------------------------------
# 3) Unexpected exception -> 500 generic message, no leak
# ---------------------------------------------------------------------------


def test_internal_errors_are_500_generic_message(client: TestClient) -> None:
    """Unexpected exceptions return 500 with a generic message and no internals leaked."""

    async def kaboom():  # pragma: no cover - exercised via client
        raise ValueError("backend failed with stack that should not leak")

    with temp_route("/_raise_internal", method="GET", handler=kaboom):
        resp = client.get("/_raise_internal")

    assert resp.status_code == 500
    data = resp.json()

    assert set(data.keys()) == {"error", "code", "details"}
    assert data["error"] == "Internal Server Error"
    assert data["code"] == 500
    # do not leak original message or a Python stack
    assert data["details"] is None
    assert "detail" not in data
