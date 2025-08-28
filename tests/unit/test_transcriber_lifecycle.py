# tests/unit/test_transcriber_lifecycle.py
"""
Unit tests for WhisperTranscriber using a lean, behavior-first contract.
All tests are fast, isolated, and avoid real filesystem/network I/O.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pytest

from app.transcribe import WhisperTranscriber

# ------------------------------ Fixtures ---------------------------------


@pytest.fixture
def transcriber() -> WhisperTranscriber:
    """Return a fresh transcriber with a dummy repo name."""
    return WhisperTranscriber(model_repo="dummy-repo")


@pytest.fixture
def no_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run asyncio.to_thread inline to avoid thread scheduling in unit tests."""

    async def _inline(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr("app.transcribe.asyncio.to_thread", _inline)


@pytest.fixture
def fake_tempfile(monkeypatch: pytest.MonkeyPatch) -> Tuple[List[str], List[str]]:
    """
    Patch tempfile + unlink to avoid disk I/O, while letting us assert cleanup.
    Returns (created_names, unlinked_names).
    """
    created: List[str] = []
    unlinked: List[str] = []

    class _FakeTmp:
        def __init__(self, *, suffix: str, delete: bool) -> None:
            self.name = f"/tmp/fake{suffix or '.wav'}"
            created.append(self.name)
            self._buffer: bytearray = bytearray()

        def write(self, data: bytes) -> int:
            self._buffer.extend(data)
            return len(data)

        # Context manager protocol
        def __enter__(self) -> "_FakeTmp":
            return self

        def __exit__(self, *_exc: Any) -> None:
            return None

    def _fake_ntf(*_args: Any, **kwargs: Any) -> _FakeTmp:
        return _FakeTmp(
            suffix=kwargs.get("suffix", ".wav"),
            delete=kwargs.get("delete", False),
        )

    def _fake_unlink(self, *, missing_ok: bool = False) -> None:
        # Record the path that would be removed
        unlinked.append(str(self))

    monkeypatch.setattr("app.transcribe.tempfile.NamedTemporaryFile", _fake_ntf)
    monkeypatch.setattr("app.transcribe.Path.unlink", _fake_unlink, raising=False)

    return created, unlinked


# ------------------------------ Tests ------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_transcribe_raises_when_not_initialized(transcriber: WhisperTranscriber):
    """transcribe() must raise if initialize() hasn't been called."""
    with pytest.raises(RuntimeError, match="not initialized"):
        await transcriber.transcribe(b"RIFF....", "test.wav")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialize_allows_and_cleanup_restricts(
    transcriber: WhisperTranscriber,
    no_threads: None,
    fake_tempfile: Tuple[List[str], List[str]],
    monkeypatch: pytest.MonkeyPatch,
):
    """
    After initialize(), transcribe is permitted; after cleanup(), it must raise
    again. No backend/network is touched.
    """
    created, unlinked = fake_tempfile

    # FIX: Match mlx_whisper.transcribe signature exactly
    def _fake_tx(
        audio: str,  # First positional arg - the audio file path
        path_or_hf_repo: str = None,  # Model repo
        **kwargs: Any,  # Accept any other kwargs
    ) -> Dict[str, Any]:
        assert audio.endswith(".wav")
        assert path_or_hf_repo == "dummy-repo"
        return {"text": ""}

    monkeypatch.setattr("app.transcribe.mlx_whisper.transcribe", _fake_tx)

    # Not initialized: must fail.
    with pytest.raises(RuntimeError):
        await transcriber.transcribe(b"\x00\x01", "a.wav")

    # Initialize → allowed.
    await transcriber.initialize()
    text = await transcriber.transcribe(b"\x00\x01", "a.wav")
    assert text == ""
    # Temp file was created and cleaned up.
    assert len(created) == 1
    assert created[0].endswith(".wav")
    assert unlinked == created  # same path removed

    # Cleanup → restricted again.
    await transcriber.cleanup()
    with pytest.raises(RuntimeError):
        await transcriber.transcribe(b"\x00\x01", "a.wav")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_backend_error_is_wrapped(
    transcriber: WhisperTranscriber,
    no_threads: None,
    fake_tempfile: Tuple[List[str], List[str]],
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Errors from the backend are surfaced as clear application errors
    (e.g., RuntimeError) without leaking backend internals.
    """

    # Patch backend to raise a generic error.
    def _boom(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        raise ValueError("backend failed with details that should not leak")

    monkeypatch.setattr("app.transcribe.mlx_whisper.transcribe", _boom)

    await transcriber.initialize()
    with pytest.raises(RuntimeError):
        await transcriber.transcribe(b"\x00\x01", "a.wav")
