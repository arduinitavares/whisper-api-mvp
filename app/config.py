# app/config.py
"""Configuration settings for the Whisper API service."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any, FrozenSet, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LogLevel(str, Enum):
    """Supported log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):  # pylint: disable=too-few-public-methods
    """Application settings loaded from environment variables."""

    # Authentication Settings
    # NOTE: Authentication is automatically enabled when RAPIDAPI_PROXY_SECRET is set
    RAPIDAPI_PROXY_SECRET: Optional[str] = Field(
        default=None,
        description=(
            "RapidAPI proxy secret for verification. "
            "When set, authentication is automatically enforced."
        ),
    )

    DEPLOYMENT_PLATFORM: str = Field(
        default="self-hosted", description="Platform: rapidapi, zapier, self-hosted"
    )

    # Model settings
    MODEL_NAME: str = Field(
        default="mlx-community/whisper-large-v3-mlx",
        description="MLX Whisper model name.",
    )

    # Concurrency settings
    MAX_CONCURRENT_JOBS: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Maximum concurrent transcription jobs.",
    )
    SEMAPHORE_TIMEOUT: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Semaphore acquisition timeout (seconds).",
    )

    # File handling settings
    MAX_FILE_SIZE_BYTES: int = Field(
        default=200 * 1024 * 1024,  # 200 MB
        ge=1024,
        description="Maximum file size in bytes.",
    )
    ALLOWED_EXTENSIONS: FrozenSet[str] = Field(
        default=frozenset(
            {".mp3", ".wav", ".m4a", ".flac", ".webm", ".mp4", ".avi", ".mov"}
        ),
        description="Allowed audio/video file extensions.",
    )

    # Memory management
    MAX_MEMORY_THRESHOLD: float = Field(
        default=85.0,
        ge=50.0,
        le=95.0,
        description="Memory usage threshold for request rejection (%).",
    )
    MAX_CACHE_SIZE: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Maximum cached transcription results.",
    )

    # API metadata
    API_TITLE: str = Field(
        default="Whisper Transcription API",
        description="API title for documentation.",
    )
    API_VERSION: str = Field(
        default="1.0.0",
        description="API version.",
    )
    API_DESCRIPTION: str = Field(
        default="High-performance audio transcription using MLX Whisper.",
        description="API description for documentation.",
    )

    # Server settings
    HOST: str = Field(
        default="0.0.0.0",
        description="Server bind host.",
    )
    PORT: int = Field(
        default=8000,
        ge=1024,
        le=65535,
        description="Server bind port.",
    )

    # Rate limiting (future)
    DEFAULT_RATE_LIMIT: int = Field(
        default=10,
        ge=1,
        description="Default requests per hour for free tier.",
    )
    PREMIUM_RATE_LIMIT: int = Field(
        default=1000,
        ge=1,
        description="Requests per hour for premium tier.",
    )

    # Logging settings
    LOG_LEVEL: LogLevel = Field(
        default=LogLevel.INFO,
        description="Logging level.",
    )
    LOG_FILE: Path = Field(
        default=Path("logs/requests.log"),
        description="Request log file path.",
    )

    # Mac Studio optimizations
    METAL_DEVICE_WRAPPER: str = Field(
        default="1",
        description="Enable explicit Metal targeting.",
    )
    PREVENT_SLEEP: bool = Field(
        default=True,
        description="Prevent system sleep during operation.",
    )

    # Development settings
    DEBUG: bool = Field(
        default=False,
        description="Enable debug mode.",
    )
    RELOAD: bool = Field(
        default=False,
        description="Enable auto-reload in development.",
    )

    # Pydantic v2 configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    def __init__(self, **data: Any) -> None:
        """Initialize settings and set environment variables."""
        super().__init__(**data)

        # MLX/Metal runtime environment tuning.
        os.environ["METAL_DEVICE_WRAPPER"] = self.METAL_DEVICE_WRAPPER
        os.environ["MLX_NUM_THREADS"] = str(self.MAX_CONCURRENT_JOBS)
        os.environ["MLX_MMAP_THRESHOLD"] = "1073741824"  # 1 GB

    @property
    def is_production(self) -> bool:
        """Return True if running in production mode."""
        return not self.DEBUG and not self.RELOAD

    @property
    def auth_enabled(self) -> bool:
        """Return True if authentication is enabled (secret is configured)."""
        return self.RAPIDAPI_PROXY_SECRET is not None

    def get_log_config(self) -> dict:
        """Return a logging configuration dictionary."""
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
                },
                "detailed": {
                    "format": (
                        "%(asctime)s %(name)s %(levelname)s "
                        "%(filename)s:%(lineno)d %(message)s"
                    ),
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": getattr(self.LOG_LEVEL, "value", "INFO"),
                    "formatter": "default",
                },
                "file": {
                    "class": "logging.FileHandler",
                    "filename": str(self.LOG_FILE),
                    "level": getattr(self.LOG_LEVEL, "value", "INFO"),
                    "formatter": "detailed",
                },
            },
            "loggers": {
                "": {
                    "level": getattr(self.LOG_LEVEL, "value", "INFO"),
                    "handlers": ["console", "file"],
                    "propagate": False,
                },
            },
        }
