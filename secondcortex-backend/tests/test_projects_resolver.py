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
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_resolve_exact_fingerprint_match_returns_resolved(client: TestClient) -> None:
    headers = _signup(client, "resolve-exact")
    create_response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "name": "Repo One",
            "workspaceName": "repo-one",
            "workspacePathHash": "abc123",
            "repoRemote": "git@github.com:acme/repo-one.git",
        },
    )
    assert create_response.status_code == 200
    project_id = create_response.json()["id"]

    response = client.post(
        "/api/v1/projects/resolve",
        headers=headers,
        json={
            "workspaceName": "repo-one",
            "workspacePathHash": "abc123",
            "repoRemote": "git@github.com:acme/repo-one.git",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "resolved"
    assert payload["projectId"] == project_id
    assert payload["confidence"] >= 0.9
    assert payload["needsSelection"] is False


def test_resolve_ambiguous_candidates_returns_needs_selection(client: TestClient) -> None:
    headers = _signup(client, "resolve-ambiguous")

    for suffix in ["A", "B"]:
        create_response = client.post(
            "/api/v1/projects",
            headers=headers,
            json={
                "name": f"Repo {suffix}",
                "workspaceName": "shared-workspace",
            },
        )
        assert create_response.status_code == 200

    response = client.post(
        "/api/v1/projects/resolve",
        headers=headers,
        json={"workspaceName": "shared-workspace"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ambiguous"
    assert payload["projectId"] is None
    assert payload["needsSelection"] is True
    assert len(payload["candidates"]) >= 2


def test_resolve_no_candidates_returns_unresolved(client: TestClient) -> None:
    headers = _signup(client, "resolve-none")

    response = client.post(
        "/api/v1/projects/resolve",
        headers=headers,
        json={
            "workspaceName": "does-not-exist",
            "workspacePathHash": "hash-not-found",
            "repoRemote": "https://github.com/acme/none.git",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unresolved"
    assert payload["projectId"] is None
    assert payload["needsSelection"] is True
    assert payload["candidates"] == []
