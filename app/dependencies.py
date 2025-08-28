# app/dependencies.py
"""Authentication dependencies for the Whisper API."""

from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, status
from pydantic import BaseModel

from app.config import Settings


class UserContext(BaseModel):
    """User context extracted from RapidAPI headers."""

    user: str
    subscription: str


async def get_user_context(
    x_rapidapi_proxy_secret: Optional[str] = Header(None),
    x_rapidapi_user: Optional[str] = Header(None),
    x_rapidapi_subscription: Optional[str] = Header(None),
) -> UserContext:
    """
    Extract user context from RapidAPI headers with authentication.

    Validates the proxy secret and returns user information.
    """
    settings = Settings()

    # Check if authentication is required
    if settings.auth_enabled:
        # Validate proxy secret
        if not x_rapidapi_proxy_secret:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing RapidAPI proxy secret",
            )

        if x_rapidapi_proxy_secret != settings.RAPIDAPI_PROXY_SECRET:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid RapidAPI proxy secret",
            )

        # Validate user header when auth is enabled
        if not x_rapidapi_user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing RapidAPI user",
            )

    # Return user context with defaults for missing headers
    return UserContext(
        user=x_rapidapi_user or "anonymous",
        subscription=x_rapidapi_subscription or "FREE",
    )


async def verify_api_key_optional(
    x_rapidapi_proxy_secret: Optional[str] = Header(None),
    x_rapidapi_user: Optional[str] = Header(None),
) -> dict:
    """
    Simple auth check for RapidAPI.

    For MVP: Just checks if secret matches when provided.
    """
    settings = Settings()

    # If auth is disabled, allow everything
    if not settings.auth_enabled:
        return {"user": x_rapidapi_user or "anonymous", "authenticated": False}

    # If auth is required, check the secret
    if not x_rapidapi_proxy_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing RapidAPI authentication",
        )

    if x_rapidapi_proxy_secret != settings.RAPIDAPI_PROXY_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid RapidAPI secret"
        )

    return {"user": x_rapidapi_user or "anonymous", "authenticated": True}
