"""
Pydantic models for API request/response validation.

Defines the data structures used for API responses including
transcription results, health checks, and metrics.
"""

from typing import Optional

from pydantic import BaseModel, Field


class TranscriptionResponse(BaseModel):
    """Response model for successful transcription."""

    text: str = Field(
        ...,
        description="Transcribed text from the audio file",
        example="Hello, this is a sample transcription.",
    )


class ErrorResponse(BaseModel):
    """Response model for API errors."""

    detail: str = Field(
        ...,
        description="Error message describing what went wrong",
        example="File size exceeds maximum allowed size",
    )


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""

    status: str = Field(
        ...,
        description="Service status indicator",
        example="ok",
    )
    memory_percent: float = Field(
        ...,
        description="Current system memory usage percentage",
        ge=0.0,
        le=100.0,
        example=45.2,
    )
    active_tasks: int = Field(
        ...,
        description="Number of currently active transcription tasks",
        ge=0,
        example=2,
    )


class MetricsResponse(BaseModel):
    """Response model for metrics endpoint."""

    total_requests: int = Field(
        ...,
        description="Total number of requests received",
        ge=0,
        example=1542,
    )
    accepted_requests: int = Field(
        ...,
        description="Number of successfully processed requests",
        ge=0,
        example=1489,
    )
    rejected_requests: int = Field(
        ...,
        description="Number of rejected requests (rate limited, errors, etc.)",
        ge=0,
        example=53,
    )
    avg_processing_time_ms: float = Field(
        ...,
        description="Average processing time in milliseconds",
        ge=0.0,
        example=2847.5,
    )


class ConfigSettings(BaseModel):
    """Configuration model for validation."""

    model_name: str = Field(
        default="mlx-community/whisper-large-v3-mlx",
        description="MLX Whisper model name to use",
    )
    max_concurrent_jobs: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Maximum number of concurrent transcription jobs",
    )
    max_file_size_bytes: int = Field(
        default=200 * 1024 * 1024,  # 200MB
        ge=1024,
        description="Maximum allowed file size in bytes",
    )
    max_memory_threshold: float = Field(
        default=85.0,
        ge=50.0,
        le=95.0,
        description="Memory usage threshold percentage for rejection",
    )
    semaphore_timeout: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Timeout in seconds for semaphore acquisition",
    )
    max_cache_size: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Maximum number of cached transcription results",
    )
