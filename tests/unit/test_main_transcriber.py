# tests/unit/test_main_transcriber.py


"""
Contract tests for app.main wiring.

Goals (TDD contracts):
- The global `transcriber` is exported and configured from `settings.MODEL_NAME`.
- The concurrency semaphore is created lazily and honors `settings.MAX_CONCURRENT_JOBS`.
"""

from __future__ import annotations

import asyncio
import importlib

import pytest

import app.main as app_main


def test_transcriber_uses_settings_model_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Contract: main.transcriber must be constructed using settings.MODEL_NAME.
    If someone hardcodes a repo string in main.py, this test will fail.
    """

    # Ensure fresh module state in case previous tests touched the globals.
    importlib.reload(app_main)

    assert hasattr(app_main, "transcriber"), "main.transcriber must be exported"
    assert app_main.transcriber.model_repo == app_main.settings.MODEL_NAME


def test_semaphore_respects_max_concurrent_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Contract: _ensure_semaphore() creates a semaphore sized from settings.MAX_CONCURRENT_JOBS.
    """

    importlib.reload(app_main)

    # Pick a non-default value to ensure the test is meaningful.
    desired_permits = 7
    monkeypatch.setattr(
        app_main.settings, "MAX_CONCURRENT_JOBS", desired_permits, raising=True
    )

    # Force re-creation of the semaphore.
    app_main.transcription_semaphore = None  # type: ignore[attr-defined]
    sem = app_main._ensure_semaphore(app_main.app)  # pylint: disable=protected-access

    # The internal counter should match the configured permits.
    current_value = getattr(sem, "_value", None)
    assert isinstance(sem, asyncio.Semaphore)
    assert (
        current_value == desired_permits
    ), f"Semaphore should start with {desired_permits} permits"
