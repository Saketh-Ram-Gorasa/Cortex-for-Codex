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


def test_decision_archaeology_filters_snapshots_by_project_id(client: TestClient, monkeypatch) -> None:
    import main

    headers = _signup_headers(client, "arch-project")
    project_a = client.post("/api/v1/projects", headers=headers, json={"name": "A"}).json()["id"]
    project_b = client.post("/api/v1/projects", headers=headers, json={"name": "B"}).json()["id"]

    ts = datetime.now(timezone.utc).isoformat()

    async def fake_timeline(limit: int = 800, user_id: str | None = None, project_id: str | None = None):
        snapshots = [
            {"id": "s1", "timestamp": ts, "active_file": "src/service.py", "summary": "A", "project_id": project_a, "git_branch": "main", "terminal_commands": "[]"},
            {"id": "s2", "timestamp": ts, "active_file": "src/service.py", "summary": "B", "project_id": project_b, "git_branch": "main", "terminal_commands": "[]"},
        ]
        if project_id:
            return [snapshot for snapshot in snapshots if snapshot.get("project_id") == project_id]
        return snapshots

    async def fake_semantic_search(query: str, top_k: int = 6, user_id: str | None = None, project_id: str | None = None):
        return await fake_timeline(project_id=project_id)

    captured_project_ids: list[str | None] = []

    async def fake_synthesize(symbol_name: str, commit_message: str, snapshots: list[dict]):
        for snapshot in snapshots:
            captured_project_ids.append(snapshot.get("project_id"))
        return "scoped", ["main"], [], 0.8

    monkeypatch.setattr(main.vector_db, "get_snapshot_timeline", fake_timeline)
    monkeypatch.setattr(main.vector_db, "semantic_search", fake_semantic_search)
    monkeypatch.setattr(main, "_synthesize_decision_history", fake_synthesize)

    response = client.post(
        "/api/v1/decision-archaeology",
        headers=headers,
        json={
            "filePath": "src/service.py",
            "symbolName": "do_work",
            "signature": "def do_work():",
            "commitHash": "abc123",
            "commitMessage": "message",
            "author": "me",
            "timestamp": ts,
            "projectId": project_a,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["found"] is True
    assert captured_project_ids
    assert set(captured_project_ids) == {project_a}
