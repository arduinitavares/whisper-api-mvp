"""Compatibility shim so imports from app.settings keep working."""

from __future__ import annotations

from functools import lru_cache

from app.config import Settings


@lru_cache
def get_settings() -> Settings:
    """Return cached settings loaded from the environment."""
    return Settings()
