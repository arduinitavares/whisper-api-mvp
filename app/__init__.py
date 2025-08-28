"""
Whisper API application package.

High-performance audio transcription service using MLX-accelerated
Whisper models optimized for Mac Studio M3 Ultra.
"""

__version__ = "1.0.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"
__description__ = "MLX-powered Whisper transcription API for Mac Studio"

# Package imports for convenience
from app.config import Settings
from app.models import (
    TranscriptionResponse,
    HealthResponse,
    MetricsResponse,
    ErrorResponse,
)

__all__ = [
    "Settings",
    "TranscriptionResponse",
    "HealthResponse", 
    "MetricsResponse",
    "ErrorResponse",
]