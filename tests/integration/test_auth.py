# tests/integration/test_auth.py
"""Integration tests for endpoint authentication."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

# A secret used just for this test
VALID_SECRET = "a-secure-secret-for-testing"


def test_transcribe_endpoint_rejects_missing_secret(
    monkeypatch, synthetic_wav_1s: bytes
):
    """Verify that POST /v1/transcribe returns 403 if the secret is missing."""
    # Set the required secret in the environment for the app to check against
    monkeypatch.setenv("RAPIDAPI_PROXY_SECRET", VALID_SECRET)

    # Create a new client to ensure env vars are loaded
    client = TestClient(app)
    files = {"file": ("test.wav", synthetic_wav_1s, "audio/wav")}

    # Make a request WITHOUT the required headers
    response = client.post("/v1/transcribe", files=files)

    # Should return 403 when auth is required but headers are missing
    assert response.status_code == 403
    data = response.json()
    assert data["code"] == 403
    assert "authentication" in data["details"].lower()


def test_transcribe_endpoint_rejects_incorrect_secret(
    monkeypatch, synthetic_wav_1s: bytes
):
    """Verify that POST /v1/transcribe returns 403 if the secret is incorrect."""
    monkeypatch.setenv("RAPIDAPI_PROXY_SECRET", VALID_SECRET)

    # Create a new client to ensure env vars are loaded
    client = TestClient(app)
    files = {"file": ("test.wav", synthetic_wav_1s, "audio/wav")}
    headers = {"X-RapidAPI-Proxy-Secret": "this-is-the-wrong-secret"}

    response = client.post("/v1/transcribe", files=files, headers=headers)

    assert response.status_code == 403
    data = response.json()
    assert data["code"] == 403
    assert "secret" in data["details"].lower()


def test_transcribe_endpoint_accepts_valid_secret(monkeypatch, synthetic_wav_1s: bytes):
    """Verify that POST /v1/transcribe works with valid secret."""
    monkeypatch.setenv("RAPIDAPI_PROXY_SECRET", VALID_SECRET)

    client = TestClient(app)
    files = {"file": ("test.wav", synthetic_wav_1s, "audio/wav")}
    headers = {
        "X-RapidAPI-Proxy-Secret": VALID_SECRET,
        "X-RapidAPI-User": "test-user",
    }

    response = client.post("/v1/transcribe", files=files, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert "text" in data
