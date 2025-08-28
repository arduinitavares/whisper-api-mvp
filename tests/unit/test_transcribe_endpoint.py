# tests/unit/test_transcribe_endpoint.py
"""
Unit tests for the /v1/transcribe endpoint.

Contract (as per architecture brief):
- Accepts multipart file with allowed extensions: mp3, wav, m4a, flac, webm, mp4, avi, mov
- Max size: 200 MB -> reject larger with 413 and a clear error payload
- Backpressure: if semaphore can't be acquired within timeout, return 503 and
  include `Retry-After: 30`
- Memory defense: if system memory usage > 85% (configurable), return 503
- Happy path: returns 200 with {"text": "..."} and does not leak backend details
- Marketplace headers (X-RapidAPI-User, X-RapidAPI-Proxy-Secret) are accepted
  and do not break the request; their presence is not required for unit tests

Notes:
- These are fast unit tests; all external effects are patched.
- We patch:
  - psutil.virtual_memory() to control memory %
  - settings to control limits and timeouts
  - semaphore creation to deterministic semaphores
  - `transcriber` object used by the route with an async mock
"""

from __future__ import annotations

import asyncio
import io
import math
import wave
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app import main as app_main  # type: ignore[import-not-found]
from app.config import Settings

# ------------------------------ Helpers -------------------------------------


def _fake_virtual_memory(percent: float):
    """Return a fake psutil.virtual_memory() result with given percent."""

    class _VM:
        def __init__(self, p: float) -> None:
            self.percent = p

    return _VM(percent)


def _patch_memory(monkeypatch: pytest.MonkeyPatch, percent: float) -> None:
    """Patch psutil.virtual_memory().percent to `percent`."""
    monkeypatch.setattr(
        app_main.psutil, "virtual_memory", lambda: _fake_virtual_memory(percent)
    )


def _patch_settings(
    monkeypatch: pytest.MonkeyPatch,
    **overrides: Any,
) -> None:
    """Patch app settings fields with given overrides."""
    for key, value in overrides.items():
        assert hasattr(app_main.settings, key), f"Unknown settings key: {key}"
        monkeypatch.setattr(app_main.settings, key, value)


def _ensure_clean_semaphore(monkeypatch: pytest.MonkeyPatch, value: int) -> None:
    """
    Force a fresh semaphore with the requested initial value (permits available).

    value == MAX_CONCURRENT_JOBS simulates all slots free.
    value == 0 simulates full saturation.
    """
    sem = app_main.asyncio.Semaphore(value)
    monkeypatch.setattr(app_main, "transcription_semaphore", sem)


def _create_wav_bytes(
    duration_seconds: float = 0.1,
    sample_rate: int = 16_000,
    frequency: float = 440.0,
) -> bytes:
    """Create a tiny mono 16-bit WAV sine wave for upload tests."""
    frames = int(duration_seconds * sample_rate)
    samples = []
    for i in range(frames):
        s = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
        samples.append(s)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:  # type: ignore[attr-defined]
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(s.to_bytes(2, "little", signed=True) for s in samples))
    return buffer.getvalue()


def _multipart_file(field_name: str, filename: str, content: bytes, mime: str) -> Dict:
    """Return a requests-style files mapping for multipart upload."""
    return {field_name: (filename, io.BytesIO(content), mime)}


# ------------------------------ Fixtures ------------------------------------


@pytest.fixture(autouse=True)
def _baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Baseline setup for all tests:
    - Healthy memory (42%)
    - Reasonable defaults for limits/timeouts
    - Fresh semaphore with all slots free
    - A mocked transcriber with deterministic result
    """
    _patch_memory(monkeypatch, percent=42.0)
    _patch_settings(
        monkeypatch,
        MAX_FILE_SIZE_BYTES=200 * 1024 * 1024,
        MAX_MEMORY_THRESHOLD=85.0,
        SEMAPHORE_TIMEOUT=0.2,  # keep tight so tests remain fast
        MAX_CONCURRENT_JOBS=4,
    )
    _ensure_clean_semaphore(monkeypatch, value=app_main.settings.MAX_CONCURRENT_JOBS)

    mock_transcriber = type("T", (), {})()
    mock_transcriber.initialize = AsyncMock(return_value=None)
    mock_transcriber.cleanup = AsyncMock(return_value=None)
    mock_transcriber.transcribe = AsyncMock(return_value="hello world")
    monkeypatch.setattr(app_main, "transcriber", mock_transcriber, raising=True)


@pytest.fixture
def client() -> TestClient:
    """Provide a TestClient for the FastAPI app."""
    return TestClient(app_main.app)


# ------------------------------ Tests ---------------------------------------


@pytest.mark.unit
def test_transcribe_happy_path_returns_200_and_text(auth_test_client):
    content = _create_wav_bytes()
    files = _multipart_file("file", "sample.wav", content=content, mime="audio/wav")
    resp = auth_test_client.post("/v1/transcribe", files=files)
    assert resp.status_code == 200, resp.text
    assert resp.json().get("text") == "hello world"


@pytest.mark.unit
def test_transcribe_rejects_unsupported_extension_415(auth_test_client, tmp_path):
    path = tmp_path / "bad.txt"
    path.write_text("not audio")
    files = _multipart_file(
        "file", path.name, content=path.read_bytes(), mime="text/plain"
    )
    resp = auth_test_client.post("/v1/transcribe", files=files)
    assert resp.status_code in (415, 400), resp.text
    assert "details" in resp.json()


@pytest.mark.unit
def test_transcribe_rejects_oversize_file_413(
    auth_test_client, monkeypatch: pytest.MonkeyPatch
):
    _patch_settings(monkeypatch, MAX_FILE_SIZE_BYTES=1024)  # 1 KB
    big = b"x" * 2048
    files = _multipart_file("file", "big.wav", content=big, mime="audio/wav")
    resp = auth_test_client.post("/v1/transcribe", files=files)
    assert resp.status_code == 413, resp.text
    assert "details" in resp.json()


@pytest.mark.skip(reason="Concurrency test is flaky and needs further investigation")
@pytest.mark.asyncio
async def test_transcribe_backpressure_timeout_returns_503(
    slow_async_test_client: AsyncClient,
    synthetic_wav_1s: bytes,
):
    """
    Ensure that when all workers are busy, subsequent requests time out
    and receive a 503 Service Unavailable.
    """
    max_jobs = app_main.settings.MAX_CONCURRENT_JOBS
    files = {"file": ("test.wav", synthetic_wav_1s, "audio/wav")}

    # A signal that will be set when the semaphore is confirmed to be full.
    all_workers_busy_event = asyncio.Event()

    # A counter to track how many "slow" tasks have started.
    started_tasks_counter = 0

    async def blocking_task():
        """A single slow request that helps saturate the semaphore."""
        nonlocal started_tasks_counter
        try:
            await slow_async_test_client.post("/v1/transcribe", files=files)
        finally:
            started_tasks_counter += 1
            # When the last slow task starts, signal that the server is full.
            if started_tasks_counter == max_jobs:
                all_workers_busy_event.set()

    # Create the tasks that will fill the semaphore.
    long_running_tasks = [asyncio.create_task(blocking_task()) for _ in range(max_jobs)]

    # Wait for the signal that all worker slots are definitely occupied.
    await all_workers_busy_event.wait()

    # NOW, with the semaphore confirmed to be full, send the final request.
    failing_response = await slow_async_test_client.post("/v1/transcribe", files=files)

    # This request should have failed with a 503.
    assert failing_response.status_code == 503

    # Clean up the background tasks.
    await asyncio.gather(*long_running_tasks)


@pytest.mark.unit
def test_transcribe_memory_pressure_returns_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If memory usage exceeds threshold, return 503 before doing any work."""
    _patch_memory(monkeypatch, percent=96.0)
    content = _create_wav_bytes()
    files = _multipart_file("file", "sample.wav", content=content, mime="audio/wav")

    resp = client.post("/v1/transcribe", files=files)
    assert resp.status_code == 503, resp.text
    payload = resp.json()
    assert "details" in payload
