# app/transcribe.py
"""
Async transcription logic using MLX Whisper.

Optimized based on mlx-whisper requirements:
- Ensures ffmpeg is available (required by mlx_whisper)
- Handles audio preprocessing automatically via mlx_whisper
- Proper error handling and diagnostic messages
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import mlx_whisper

logger = logging.getLogger(__name__)


def check_ffmpeg_installed() -> bool:
    """Check if ffmpeg is installed and available in PATH."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


class WhisperTranscriber:
    """Transcribes audio using MLX-optimized Whisper models."""

    def __init__(
        self,
        model_repo: str = "mlx-community/whisper-large-v3-mlx",
        *,
        word_timestamps: bool = False,
        language: Optional[str] = None,
    ) -> None:
        """
        Initialize the transcriber.

        Args:
            model_repo: HuggingFace repo with MLX-optimized Whisper model
            word_timestamps: Whether to generate word-level timestamps
            language: Force language detection (None for auto-detect)
        """
        self.model_repo = model_repo
        self.word_timestamps = word_timestamps
        self.language = language
        self._initialized: bool = False

        # Check ffmpeg on initialization
        if not check_ffmpeg_installed():
            logger.warning(
                "ffmpeg not found in PATH. Audio transcription may fail. "
                "Install with: brew install ffmpeg"
            )

    async def initialize(self) -> None:
        """
        Mark the transcriber as ready and verify dependencies.

        Note: mlx_whisper loads models on-demand during transcription,
        so we don't preload here to avoid memory waste.
        """
        if self._initialized:
            return

        # Verify ffmpeg is available (critical dependency)
        if not check_ffmpeg_installed():
            raise RuntimeError(
                "ffmpeg is required but not found. "
                "Install it with: brew install ffmpeg"
            )

        # Verify model repo format
        if "/" not in self.model_repo:
            logger.warning(
                "Model repo '%s' doesn't look like a HuggingFace repo. Expected format: 'organization/model-name'",
                self.model_repo,
            )

        self._initialized = True
        logger.info("Transcriber initialized with model: %s", self.model_repo)

    async def cleanup(self) -> None:
        """Reset readiness state."""
        self._initialized = False

    async def transcribe(self, audio_bytes: bytes, filename: str) -> str:
        """
        Transcribe audio bytes and return recognized text.

        Args:
            audio_bytes: Raw audio file bytes in any ffmpeg-supported format
            filename: Original filename (used for extension detection)

        Returns:
            Transcribed text string

        Raises:
            RuntimeError: If transcriber not initialized or transcription fails
        """
        if not self._initialized:
            raise RuntimeError("Transcriber not initialized")

        # Determine file extension for temp file
        suffix = Path(filename).suffix.lower()
        # Ensure we have a valid audio extension
        if suffix not in {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".mp4", ".webm"}:
            logger.warning("Unusual audio extension: %s, defaulting to .wav", suffix)
            suffix = ".wav"

        # Write audio to temporary file
        # mlx_whisper needs a file path, not bytes
        with tempfile.NamedTemporaryFile(
            suffix=suffix, delete=False, prefix="whisper_"
        ) as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)

        def _run_transcription() -> Dict[str, Any]:
            """
            Run mlx_whisper transcription in a thread.

            mlx_whisper handles all preprocessing internally:
            - Uses ffmpeg to decode any supported format
            - Resamples to 16kHz automatically
            - Converts to mono automatically
            - Processes in 30-second chunks
            """
            try:
                # *** MODIFICATION: Set verbose=True to debug model issues ***
                logger.info(
                    "Starting transcription for %s with mlx_whisper...", tmp_path
                )
                result = mlx_whisper.transcribe(
                    audio=str(tmp_path),
                    path_or_hf_repo=self.model_repo,
                    word_timestamps=self.word_timestamps,
                    language=self.language,
                    verbose=True,  # Enable detailed logging from the library
                )
                logger.info("mlx_whisper completed for %s.", tmp_path)
                return result
            except FileNotFoundError as e:
                if "ffmpeg" in str(e).lower():
                    raise RuntimeError(
                        "ffmpeg not found. Install with: brew install ffmpeg"
                    ) from e
                raise
            except Exception as e:
                # Log the actual error for debugging
                logger.error("mlx_whisper call failed: %s", e, exc_info=True)
                raise

        try:
            # Run transcription in thread pool to avoid blocking
            result = await asyncio.to_thread(_run_transcription)

            # Extract text from result
            text = result.get("text", "").strip()

            # Log success with basic stats
            logger.info(
                "Transcribed %.1fKB audio (%s) -> %d chars",
                len(audio_bytes) / 1024,
                suffix,
                len(text),
            )

            return text

        except RuntimeError:
            # Re-raise RuntimeError as-is (already has good message)
            raise
        except Exception as exc:
            # Wrap other exceptions with context
            logger.error("Transcription failed for %s: %s", filename, exc)
            raise RuntimeError(f"Transcription failed: {str(exc)}") from exc
        finally:
            # Always clean up temp file
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError as e:
                logger.warning("Failed to delete temp file %s: %s", tmp_path, e)
