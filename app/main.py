# app/main.py
"""
FastAPI application wiring for Whisper API.

Public surface:
- Safe, lazy initialization of the concurrency semaphore (via lifespan).
- /health endpoint (memory %, active task count).
- Minimal in-memory metrics + /metrics endpoint.
- /v1/transcribe: validates file, checks memory, enforces backpressure, calls
  the transcriber, and responds with JSON.

The `transcriber` global is intentionally exported so tests can monkey-patch it.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Annotated, Any, Dict, Optional

import psutil
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings
from app.dependencies import verify_api_key_optional

# TDD STEP 2: Import the new dependency and context model
from app.transcribe import WhisperTranscriber

# -----------------------------------------------------------------------------
# Settings / logger
# -----------------------------------------------------------------------------
settings = Settings()
logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Error envelope helpers (RapidAPI-friendly shape)
# -----------------------------------------------------------------------------
def _status_phrase(code: int) -> str:
    try:
        return HTTPStatus(code).phrase
    except ValueError:  # pragma: no cover
        return "Error"


def _error_envelope(
    code: int, details: Any = None, *, error: Optional[str] = None
) -> Dict[str, Any]:
    """
    Unified error shape:
        {"error": <status phrase>, "code": <int>, "details": <str|list|None>}
    """
    return {
        "error": error or _status_phrase(code),
        "code": int(code),
        "details": details,
    }


def _flatten_validation_errors(exc: RequestValidationError) -> list[str]:
    # Convert Pydantic/Starlette validation errors to a compact list of strings.
    items: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        msg = err.get("msg", "Invalid value")
        items.append(f"{loc}: {msg}" if loc else msg)
    return items or [str(exc)]


# -----------------------------------------------------------------------------
# Concurrency semaphore utils (stored on app.state; lazily ensured)
# -----------------------------------------------------------------------------
def _ensure_semaphore(app: FastAPI) -> asyncio.Semaphore:
    """Ensure a semaphore exists with MAX_CONCURRENT_JOBS permits (idempotent)."""
    sem = getattr(app.state, "transcription_semaphore", None)
    if sem is None:
        sem = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)
        app.state.transcription_semaphore = sem
    return sem


def current_active_tasks(app: FastAPI) -> int:
    """Return the number of currently acquired permits."""
    sem = _ensure_semaphore(app)
    max_permits = settings.MAX_CONCURRENT_JOBS
    current_value = getattr(sem, "_value", max_permits)  # defensive
    return max(0, max_permits - int(current_value))


# -----------------------------------------------------------------------------
# Minimal metrics store + accessors (kept trivial for unit tests)
# -----------------------------------------------------------------------------
METRICS: Dict[str, float | int] = {
    "total_requests": 0,
    "accepted_requests": 0,
    "rejected_requests": 0,
    "avg_processing_time_ms": 0.0,
}


def get_metrics() -> Dict[str, float | int]:
    """Return a shallow copy of the metrics dict."""
    return {
        "total_requests": int(METRICS.get("total_requests", 0)),
        "accepted_requests": int(METRICS.get("accepted_requests", 0)),
        "rejected_requests": int(METRICS.get("rejected_requests", 0)),
        "avg_processing_time_ms": float(METRICS.get("avg_processing_time_ms", 0.0)),
    }


def _metrics_record_request(accepted: bool, duration_ms: float) -> None:
    """Update counters and running average (O(1))."""
    METRICS["total_requests"] = int(METRICS.get("total_requests", 0)) + 1
    if accepted:
        METRICS["accepted_requests"] = int(METRICS.get("accepted_requests", 0)) + 1
    else:
        METRICS["rejected_requests"] = int(METRICS.get("rejected_requests", 0)) + 1

    total = int(METRICS["total_requests"])
    prev_avg = float(METRICS.get("avg_processing_time_ms", 0.0))
    new_avg = prev_avg + (float(duration_ms) - prev_avg) / max(total, 1)
    METRICS["avg_processing_time_ms"] = max(0.0, new_avg)


# -----------------------------------------------------------------------------
# Transcriber (exported so tests can monkey-patch app_main.transcriber)
# -----------------------------------------------------------------------------
transcriber: WhisperTranscriber = WhisperTranscriber(
    model_repo=settings.MODEL_NAME,
    word_timestamps=False,
    language=None,
)


# -----------------------------------------------------------------------------
# Lifespan (startup/shutdown)
# -----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    _ensure_semaphore(app)
    await transcriber.initialize()
    try:
        yield
    finally:
        # Add cleanup when needed (e.g., await transcriber.cleanup())
        pass


# Create app early so handlers/routes can refer to it safely
app = FastAPI(title="Whisper Transcription API", lifespan=lifespan)


# -----------------------------------------------------------------------------
# Exception handlers (registered AFTER app is created)
# -----------------------------------------------------------------------------
async def _http_exception_handler(
    _: Request, exc: StarletteHTTPException
) -> JSONResponse:
    details = None
    if exc.detail is not None:
        details = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_envelope(exc.status_code, details=details),
    )


async def _validation_exception_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    details = _flatten_validation_errors(exc)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=_error_envelope(400, details=details),
    )


async def _value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    logger.exception("Unhandled ValueError", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_envelope(status.HTTP_500_INTERNAL_SERVER_ERROR, details=None),
    )


async def _unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_envelope(status.HTTP_500_INTERNAL_SERVER_ERROR, details=None),
    )


# Register the handlers
app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
app.add_exception_handler(RequestValidationError, _validation_exception_handler)
app.add_exception_handler(ValueError, _value_error_handler)
app.add_exception_handler(Exception, _unhandled_exception_handler)


# -----------------------------------------------------------------------------
# Convenience accessor used by tests (after app exists)
# -----------------------------------------------------------------------------
def get_active_tasks() -> int:
    return current_active_tasks(app)


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.get("/health")
async def health_check() -> dict:
    """
    Report basic service health.

    Returns:
        {"status": "ok", "memory_percent": float, "active_tasks": int}
    """
    memory_percent = float(psutil.virtual_memory().percent)
    active_tasks = current_active_tasks(app)
    return {
        "status": "ok",
        "memory_percent": memory_percent,
        "active_tasks": active_tasks,
    }


@app.get("/metrics")
async def metrics() -> Dict[str, float | int]:
    """
    Return simple service metrics.

    Contract:
        {
            "total_requests": int,
            "accepted_requests": int,
            "rejected_requests": int,
            "avg_processing_time_ms": float
        }
    """
    return get_metrics()


@app.post("/v1/transcribe")
async def transcribe_endpoint(
    file: UploadFile, auth_info: dict = Depends(verify_api_key_optional)
) -> JSONResponse:
    """
    Accept an audio/video file, enforce guards, and return transcription text.

    Guards:
    - Memory pressure: return 503 if psutil reports > threshold.
    - Extension allowlist: 415 for unsupported types.
    - Size limit: 413 if > MAX_FILE_SIZE_BYTES.
    - Backpressure: 503 with Retry-After if semaphore can't be acquired quickly.
    """
    start = time.perf_counter()

    # Memory pressure defense (pre-check before work)
    mem_percent = float(psutil.virtual_memory().percent)
    if mem_percent > settings.MAX_MEMORY_THRESHOLD:
        _metrics_record_request(accepted=False, duration_ms=0.0)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service under memory pressure. Please try again later.",
        )

    # Validate extension (case-insensitive)
    filename = file.filename or "upload"
    suffix = "." + filename.split(".")[-1].lower() if "." in filename else ""
    if suffix not in settings.ALLOWED_EXTENSIONS:
        _metrics_record_request(accepted=False, duration_ms=0.0)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {suffix or 'unknown'}",
        )

    # Read bytes and enforce size
    data = await file.read()
    if len(data) > int(settings.MAX_FILE_SIZE_BYTES):
        _metrics_record_request(accepted=False, duration_ms=0.0)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds maximum allowed size.",
        )

    # Acquire concurrency slot with timeout -> 503 with envelope on timeout
    sem = _ensure_semaphore(app)
    try:
        await asyncio.wait_for(sem.acquire(), timeout=float(settings.SEMAPHORE_TIMEOUT))
    except asyncio.TimeoutError as exc:
        _metrics_record_request(accepted=False, duration_ms=0.0)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="All workers are currently busy. Please try again later.",
            headers={"Retry-After": "30"},
        ) from exc

    # Process (call into transcriber) and ensure we always release the slot
    try:
        # Hash may be used for dedup or logging; kept lightweight here.
        _ = hashlib.sha256(data).hexdigest()

        # Ensure the transcriber is ready (idempotent in our implementation).
        await transcriber.initialize()

        text = await transcriber.transcribe(data, filename)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        _metrics_record_request(accepted=True, duration_ms=elapsed_ms)
        return JSONResponse(status_code=200, content={"text": text})
    except (RuntimeError, ValueError, OSError) as exc:
        logger.exception("Transcription failed")
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        _metrics_record_request(accepted=False, duration_ms=elapsed_ms)
        # Raise so the global handlers format the unified envelope
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transcription failed.",
        ) from exc
    finally:
        sem.release()
