# tests/conftest.py
"""Shared test fixtures for the Whisper API test suite."""

from __future__ import annotations

import asyncio
import io
import math
import wave
from typing import AsyncGenerator, Dict, Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app import main as app_main
from app.main import app

# Test constants matching the dependency tests
VALID_SECRET = "test-secret"
VALID_HEADERS = {
    "X-RapidAPI-Proxy-Secret": VALID_SECRET,
    "X-RapidAPI-User": "test-user",
    "X-RapidAPI-Subscription": "PRO",
}


def _create_synthetic_wav(
    duration_seconds: float = 1.0,
    sample_rate: int = 16000,
    frequency: float = 440.0,
) -> bytes:
    """Create synthetic WAV file for testing."""
    frames = int(duration_seconds * sample_rate)
    samples = []

    for i in range(frames):
        sample = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
        samples.append(sample)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)

        wav_data = b"".join(
            sample.to_bytes(2, byteorder="little", signed=True) for sample in samples
        )
        wav_file.writeframes(wav_data)

    return buffer.getvalue()


@pytest.fixture
def synthetic_wav_1s() -> bytes:
    """Generate 1-second synthetic WAV file for testing."""
    return _create_synthetic_wav(duration_seconds=1.0)


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """Return valid authentication headers for testing."""
    return VALID_HEADERS.copy()


@pytest.fixture
def auth_test_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with authentication configured."""
    # Set the environment secret that the app will check against
    monkeypatch.setenv("RAPIDAPI_PROXY_SECRET", VALID_SECRET)

    # Create a TestClient that includes auth headers by default
    client = TestClient(app)

    # Monkey patch the post method to include auth headers
    original_post = client.post

    def post_with_auth(*args, **kwargs):
        if "headers" not in kwargs:
            kwargs["headers"] = {}
        # Add auth headers if not already present
        for key, value in VALID_HEADERS.items():
            if key not in kwargs["headers"]:
                kwargs["headers"][key] = value
        return original_post(*args, **kwargs)

    client.post = post_with_auth
    return client


@pytest.fixture
async def slow_async_test_client() -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient for concurrency/timing tests with slow transcriber."""
    # Mock the transcriber to be slow for backpressure testing
    slow_transcriber = type("SlowTranscriber", (), {})()
    slow_transcriber.initialize = AsyncMock(return_value=None)
    slow_transcriber.cleanup = AsyncMock(return_value=None)

    async def slow_transcribe(*args, **kwargs):
        await asyncio.sleep(2.0)  # Simulate slow processing
        return "slow transcription result"

    slow_transcriber.transcribe = AsyncMock(side_effect=slow_transcribe)

    # Temporarily replace the transcriber
    original_transcriber = app_main.transcriber
    app_main.transcriber = slow_transcriber

    try:
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client
    finally:
        # Restore original transcriber
        app_main.transcriber = original_transcriber


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment configuration."""
    # Ensure test-friendly settings
    import os

    os.environ["DEBUG"] = "true"
    os.environ["LOG_LEVEL"] = "ERROR"  # Reduce noise in test output


@pytest.fixture(autouse=True)
def mock_transcriber_for_tests(monkeypatch: pytest.MonkeyPatch):
    """Mock the transcriber for most tests to avoid model loading."""
    # Create a mock transcriber that behaves predictably
    mock_transcriber = type("MockTranscriber", (), {})()
    mock_transcriber.model_repo = "test-model"
    mock_transcriber.initialize = AsyncMock(return_value=None)
    mock_transcriber.cleanup = AsyncMock(return_value=None)
    mock_transcriber.transcribe = AsyncMock(return_value="hello world")

    # Replace the global transcriber with our mock
    monkeypatch.setattr(app_main, "transcriber", mock_transcriber)


# Pytest asyncio configuration
def pytest_configure(config):
    """Configure pytest for asyncio testing."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (may be slow)"
    )
    config.addinivalue_line("markers", "unit: marks tests as fast unit tests")
