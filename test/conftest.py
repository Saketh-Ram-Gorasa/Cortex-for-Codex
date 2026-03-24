"""
Shared pytest fixtures for SecondCortex CRUD tests.
Runs against FastAPI's TestClient — no live server required.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure the backend package is importable.
BACKEND_ROOT = Path(__file__).resolve().parent.parent / "secondcortex-backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("PYTEST_RUNNING", "1")


@pytest.fixture(autouse=True)
def _clear_llm_caches():
    import services.llm_client as llm_client

    llm_client._client_cache.clear()
    with llm_client._metrics_lock:
        llm_client._metrics.clear()
    yield
    llm_client._client_cache.clear()


@pytest.fixture
def client() -> TestClient:
    from main import app

    return TestClient(app)


def signup(client: TestClient, prefix: str = "user") -> dict:
    """Create a new user and return user_id + auth headers."""
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "test123", "display_name": prefix},
    )
    assert resp.status_code == 200, f"Signup failed: {resp.text}"
    payload = resp.json()
    return {
        "user_id": payload["user_id"],
        "headers": {"Authorization": f"Bearer {payload['token']}"},
    }


def create_project(client: TestClient, headers: dict, name: str = "TestProject") -> dict:
    """Helper to create a project and return the response body."""
    resp = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": name},
    )
    assert resp.status_code == 200, f"Create project failed: {resp.text}"
    return resp.json()


def create_team(client: TestClient, headers: dict, name: str = "TestTeam") -> dict:
    """Helper to create a team and return the response body."""
    resp = client.post(
        "/api/v1/teams",
        headers=headers,
        json={"name": name},
    )
    assert resp.status_code == 200, f"Create team failed: {resp.text}"
    return resp.json()
