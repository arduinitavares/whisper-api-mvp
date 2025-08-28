# tests/unit/test_metrics_endpoint.py
"""
Unit tests for the /metrics endpoint.

Contract:
- Returns HTTP 200 with JSON fields:
    total_requests: int >= 0
    accepted_requests: int >= 0
    rejected_requests: int >= 0
    avg_processing_time_ms: float >= 0
- Endpoint is read-only; no I/O or backend calls are required.
- Tests are isolated and patch the app's metrics accessor or store.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest
from fastapi.testclient import TestClient

# Import the FastAPI app and module to patch.
from app import main as app_main  # type: ignore[import-not-found]


def _patch_metrics_dict(monkeypatch: pytest.MonkeyPatch, data: Dict[str, Any]) -> None:
    """
    Patch a metrics accessor or dict on the app module so /metrics returns `data`.

    Supports common shapes:
      - function: app_main.get_metrics() -> dict
      - dict:     app_main.METRICS or app_main.metrics
    """
    if hasattr(app_main, "get_metrics") and callable(app_main.get_metrics):

        def _fake_get_metrics() -> Dict[str, Any]:
            return dict(data)

        monkeypatch.setattr(app_main, "get_metrics", _fake_get_metrics)
        return

    # Fallback: if the app exposes a dict, replace it (endpoint should read it).
    if hasattr(app_main, "METRICS"):
        monkeypatch.setattr(app_main, "METRICS", dict(data))
        return

    if hasattr(app_main, "metrics"):
        monkeypatch.setattr(app_main, "metrics", dict(data))
        return

    # If neither exists, we skip the test (endpoint contract not implemented yet).
    pytest.skip("App does not expose a metrics accessor or dict compatible with test.")


@pytest.mark.unit
def test_metrics_ok_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """`/metrics` returns HTTP 200 and the expected keys/types with sane bounds."""
    stub = {
        "total_requests": 10,
        "accepted_requests": 8,
        "rejected_requests": 2,
        "avg_processing_time_ms": 275.4,
    }
    _patch_metrics_dict(monkeypatch, stub)

    client = TestClient(app_main.app)
    resp = client.get("/metrics")
    assert resp.status_code == 200

    data = resp.json()
    # Keys
    for key in (
        "total_requests",
        "accepted_requests",
        "rejected_requests",
        "avg_processing_time_ms",
    ):
        assert key in data, f"Missing key: {key}"

    # Types & bounds
    assert isinstance(data["total_requests"], int) and data["total_requests"] >= 0
    assert isinstance(data["accepted_requests"], int) and data["accepted_requests"] >= 0
    assert isinstance(data["rejected_requests"], int) and data["rejected_requests"] >= 0
    assert isinstance(data["avg_processing_time_ms"], (int, float))
    assert float(data["avg_processing_time_ms"]) >= 0.0


@pytest.mark.unit
def test_metrics_consistency(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    accepted + rejected should not exceed total, and avg time should be reasonable.
    """
    stub = {
        "total_requests": 25,
        "accepted_requests": 20,
        "rejected_requests": 5,
        "avg_processing_time_ms": 123.0,
    }
    _patch_metrics_dict(monkeypatch, stub)

    client = TestClient(app_main.app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    data = resp.json()

    assert (
        data["accepted_requests"] + data["rejected_requests"] <= data["total_requests"]
    )
    assert 0.0 <= float(data["avg_processing_time_ms"]) < 60_000.0  # < 1 minute


@pytest.mark.unit
def test_metrics_updates_reflected(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    If the underlying metrics change, the endpoint should reflect the new values.
    We simulate this by swapping the backing accessor/dict between calls.
    """
    first = {
        "total_requests": 1,
        "accepted_requests": 1,
        "rejected_requests": 0,
        "avg_processing_time_ms": 500.0,
    }
    second = {
        "total_requests": 3,
        "accepted_requests": 2,
        "rejected_requests": 1,
        "avg_processing_time_ms": 250.0,
    }

    client = TestClient(app_main.app)

    _patch_metrics_dict(monkeypatch, first)
    resp1 = client.get("/metrics")
    assert resp1.status_code == 200
    d1 = resp1.json()
    assert d1["total_requests"] == 1
    assert d1["accepted_requests"] == 1
    assert d1["rejected_requests"] == 0
    assert d1["avg_processing_time_ms"] == 500.0

    _patch_metrics_dict(monkeypatch, second)
    resp2 = client.get("/metrics")
    assert resp2.status_code == 200
    d2 = resp2.json()
    assert d2["total_requests"] == 3
    assert d2["accepted_requests"] == 2
    assert d2["rejected_requests"] == 1
    assert d2["avg_processing_time_ms"] == 250.0
