from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from main import app

    return TestClient(app)


def _signup(client: TestClient, prefix: str) -> dict:
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "test123", "display_name": prefix},
    )
    assert response.status_code == 200
    payload = response.json()
    return {
        "user_id": payload["user_id"],
        "headers": {"Authorization": f"Bearer {payload['token']}"},
    }


def test_project_crud_visibility_and_owner_only_update(client: TestClient) -> None:
    owner = _signup(client, "owner")
    teammate = _signup(client, "teammate")

    # Owner creates project without visibility -> defaults to private.
    create_response = client.post(
        "/api/v1/projects",
        headers=owner["headers"],
        json={"name": "Alpha"},
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"] == "Alpha"
    assert created["visibility"] == "private"
    assert created["is_archived"] is False

    # Owner can patch.
    patch_response = client.patch(
        f"/api/v1/projects/{created['id']}",
        headers=owner["headers"],
        json={"name": "Alpha Renamed", "visibility": "team"},
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["name"] == "Alpha Renamed"
    assert patched["visibility"] == "team"

    # Non-owner cannot patch.
    forbidden_patch = client.patch(
        f"/api/v1/projects/{created['id']}",
        headers=teammate["headers"],
        json={"name": "Hacked"},
    )
    assert forbidden_patch.status_code == 403

    # Archive + unarchive.
    archive_response = client.post(
        f"/api/v1/projects/{created['id']}/archive",
        headers=owner["headers"],
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["is_archived"] is True

    unarchive_response = client.post(
        f"/api/v1/projects/{created['id']}/unarchive",
        headers=owner["headers"],
    )
    assert unarchive_response.status_code == 200
    assert unarchive_response.json()["is_archived"] is False


def test_project_list_returns_visible_projects(client: TestClient) -> None:
    owner = _signup(client, "owner-list")

    create_private = client.post(
        "/api/v1/projects",
        headers=owner["headers"],
        json={"name": "Private A"},
    )
    assert create_private.status_code == 200

    create_team = client.post(
        "/api/v1/projects",
        headers=owner["headers"],
        json={"name": "Team B", "visibility": "team"},
    )
    assert create_team.status_code == 200

    listing = client.get("/api/v1/projects", headers=owner["headers"])
    assert listing.status_code == 200
    projects = listing.json()["projects"]
    names = {project["name"] for project in projects}
    assert "Private A" in names
    assert "Team B" in names
