from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from main import app

    return TestClient(app)


def _signup_headers(client: TestClient, prefix: str) -> dict:
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "test123", "display_name": prefix},
    )
    assert response.status_code == 200
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_timeline_filters_by_project_id(client: TestClient, monkeypatch) -> None:
    import main

    headers = _signup_headers(client, "timeline-filter")
    project_a = client.post("/api/v1/projects", headers=headers, json={"name": "A"}).json()["id"]
    project_b = client.post("/api/v1/projects", headers=headers, json={"name": "B"}).json()["id"]

    async def fake_get_snapshot_timeline(limit: int = 200, user_id: str | None = None, project_id: str | None = None):
        ts = datetime.now(timezone.utc).isoformat()
        snapshots = [
            {"id": "1", "timestamp": ts, "active_file": "a.py", "git_branch": "main", "summary": "A", "entities": "", "project_id": project_a},
            {"id": "2", "timestamp": ts, "active_file": "b.py", "git_branch": "main", "summary": "B", "entities": "", "project_id": project_b},
        ]
        if project_id:
            return [snapshot for snapshot in snapshots if snapshot.get("project_id") == project_id]
        return snapshots

    monkeypatch.setattr(main.vector_db, "get_snapshot_timeline", fake_get_snapshot_timeline)

    response = client.get(f"/api/v1/snapshots/timeline?projectId={project_a}", headers=headers)
    assert response.status_code == 200
    timeline = response.json()["timeline"]
    assert len(timeline) == 1
    assert timeline[0]["project_id"] == project_a


def test_timeline_rejects_unauthorized_project_id(client: TestClient) -> None:
    headers_a = _signup_headers(client, "timeline-owner-a")
    headers_b = _signup_headers(client, "timeline-owner-b")

    project_b = client.post("/api/v1/projects", headers=headers_b, json={"name": "B private"}).json()["id"]

    response = client.get(f"/api/v1/snapshots/timeline?projectId={project_b}", headers=headers_a)
    assert response.status_code == 403
