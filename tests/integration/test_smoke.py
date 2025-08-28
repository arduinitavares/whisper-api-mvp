# tests/integration/test_smoke.py
"""
Integration smoke tests for the API.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_api_smoke_happy_path(
    auth_test_client: TestClient,
    synthetic_wav_1s: bytes,
) -> None:
    """
    Smoke test: POST to /v1/transcribe with a valid audio file and auth headers
    should return 200 OK with a transcription payload.
    """
    files = {"file": ("smoke_test.wav", synthetic_wav_1s, "audio/wav")}
    resp = auth_test_client.post("/v1/transcribe", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "text" in data
    assert isinstance(data["text"], str)
