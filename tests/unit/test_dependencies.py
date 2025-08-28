# tests/unit/test_dependencies.py
"""
Tests for API dependencies, focusing on RapidAPI authentication.
"""
from __future__ import annotations

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, status
from fastapi.testclient import TestClient

from app.dependencies import UserContext, get_user_context

# Build a tiny app just for the dependency
test_app = FastAPI()


@test_app.get("/test-auth")
async def _auth_endpoint_for_test(
    user: Annotated[UserContext, Depends(get_user_context)],
) -> dict:
    return {"user": user.user, "subscription": user.subscription}


@pytest.fixture
def dep_client() -> TestClient:
    # Create client per test so env/monkeypatch is in effect
    return TestClient(test_app)


VALID_SECRET = "test-secret"  # **match conftest**
VALID_HEADERS = {
    "X-RapidAPI-Proxy-Secret": VALID_SECRET,
    "X-RapidAPI-User": "test-user",
    "X-RapidAPI-Subscription": "PRO",
}


def test_auth_success_with_valid_headers(
    dep_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("RAPIDAPI_PROXY_SECRET", VALID_SECRET)
    resp = dep_client.get("/test-auth", headers=VALID_HEADERS)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json() == {"user": "test-user", "subscription": "PRO"}


def test_auth_fails_with_missing_secret(
    dep_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("RAPIDAPI_PROXY_SECRET", VALID_SECRET)
    headers = {k: v for k, v in VALID_HEADERS.items() if k != "X-RapidAPI-Proxy-Secret"}
    resp = dep_client.get("/test-auth", headers=headers)
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_auth_fails_with_incorrect_secret(
    dep_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("RAPIDAPI_PROXY_SECRET", VALID_SECRET)
    headers = dict(VALID_HEADERS, **{"X-RapidAPI-Proxy-Secret": "wrong"})
    resp = dep_client.get("/test-auth", headers=headers)
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_auth_fails_with_missing_user_header(
    dep_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("RAPIDAPI_PROXY_SECRET", VALID_SECRET)
    headers = {k: v for k, v in VALID_HEADERS.items() if k != "X-RapidAPI-User"}
    resp = dep_client.get("/test-auth", headers=headers)
    assert resp.status_code == status.HTTP_403_FORBIDDEN
