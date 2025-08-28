# tests/unit/test_health_endpoint.py
"""
Unit tests for the /health endpoint.

Contract:
- Returns HTTP 200 with a JSON body containing: status, memory_percent, active_tasks.
- memory_percent is a float (0..100); behavior is read-only (no rejection here).
- active_tasks reflects the app's notion of in-flight tasks (mocked in tests).
All tests are fast, isolated, and avoid real system I/O.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Import the FastAPI app and the module we will patch.
from app import main as app_main


def _patch_memory_percent(monkeypatch: pytest.MonkeyPatch, value: float) -> None:
    """Patch psutil.virtual_memory().percent to a fixed value."""

    def _fake_virtual_memory() -> SimpleNamespace:
        return SimpleNamespace(percent=value)

    monkeypatch.setattr(app_main.psutil, "virtual_memory", _fake_virtual_memory)


def _patch_active_tasks(monkeypatch: pytest.MonkeyPatch, value: int) -> None:
    """
    Patch the current_active_tasks function to return a fixed value.

    The real function signature is: current_active_tasks(app: FastAPI) -> int
    """

    def _fake_current_active_tasks(app: Any) -> int:
        # Ignore the app argument, just return our test value
        return value

    monkeypatch.setattr(app_main, "current_active_tasks", _fake_current_active_tasks)


@pytest.mark.unit
def test_health_ok_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """/health returns 200 and the expected JSON shape."""
    _patch_memory_percent(monkeypatch, value=42.0)
    _patch_active_tasks(monkeypatch, value=0)

    client = TestClient(app_main.app)
    resp = client.get("/health")
    assert resp.status_code == 200

    data = resp.json()
    assert data.get("status") == "ok"
    assert isinstance(data.get("memory_percent"), (int, float))
    assert 0.0 <= float(data["memory_percent"]) <= 100.0
    assert isinstance(data.get("active_tasks"), int)
    assert data["active_tasks"] >= 0


@pytest.mark.unit
def test_health_reports_high_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """/health reports high memory usage without failing the request."""
    _patch_memory_percent(monkeypatch, value=91.5)
    _patch_active_tasks(monkeypatch, value=2)

    client = TestClient(app_main.app)
    resp = client.get("/health")
    assert resp.status_code == 200

    data = resp.json()
    # Validate it reflects what psutil reported.
    assert pytest.approx(float(data["memory_percent"]), rel=0, abs=0.01) == 91.5
    assert data["status"] == "ok"
    assert data["active_tasks"] == 2


@pytest.mark.unit
def test_health_active_tasks_reflection(monkeypatch: pytest.MonkeyPatch) -> None:
    """/health reflects current active task count via supported accessor."""
    _patch_active_tasks(monkeypatch, value=7)
    _patch_memory_percent(monkeypatch, value=12.3)

    client = TestClient(app_main.app)
    resp = client.get("/health")
    assert resp.status_code == 200

    data = resp.json()
    assert data["active_tasks"] == 7
    assert data["status"] == "ok"
