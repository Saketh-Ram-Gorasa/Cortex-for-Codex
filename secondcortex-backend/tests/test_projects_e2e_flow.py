from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from main import app

    return TestClient(app)


def _signup_headers(client: TestClient, prefix: str) -> dict[str, str]:
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "test123", "display_name": prefix},
    )
    assert response.status_code == 200
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_project_scoped_timeline_and_events_isolation(client: TestClient, monkeypatch) -> None:
    import main

    headers = _signup_headers(client, "e2e-owner")
    headers_other = _signup_headers(client, "e2e-other")

    project_a = client.post("/api/v1/projects", headers=headers, json={"name": "Project A"}).json()["id"]
    project_b = client.post("/api/v1/projects", headers=headers, json={"name": "Project B"}).json()["id"]

    now = datetime.now(timezone.utc).isoformat()
    fake_rows = [
        {
            "id": "snap-a",
            "timestamp": now,
            "active_file": "src/a.py",
            "git_branch": "main",
            "summary": "A summary",
            "entities": "A",
            "project_id": project_a,
            "terminal_commands": "[]",
        },
        {
            "id": "snap-b",
            "timestamp": now,
            "active_file": "src/b.py",
            "git_branch": "main",
            "summary": "B summary",
            "entities": "B",
            "project_id": project_b,
            "terminal_commands": "[]",
        },
    ]

    async def fake_timeline(limit: int = 200, user_id: str | None = None, project_id: str | None = None):
        rows = list(fake_rows)
        if project_id:
            rows = [row for row in rows if row["project_id"] == project_id]
        return rows[:limit]

    async def fake_events(limit: int = 10, user_id: str | None = None, project_id: str | None = None):
        rows = list(fake_rows)
        if project_id:
            rows = [row for row in rows if row["project_id"] == project_id]
        return rows[:limit]

    monkeypatch.setattr(main.vector_db, "get_snapshot_timeline", fake_timeline)
    monkeypatch.setattr(main.vector_db, "get_recent_snapshots", fake_events)

    timeline_a = client.get(f"/api/v1/snapshots/timeline?projectId={project_a}", headers=headers)
    assert timeline_a.status_code == 200
    timeline_rows = timeline_a.json()["timeline"]
    assert len(timeline_rows) == 1
    assert timeline_rows[0]["project_id"] == project_a

    events_b = client.get(f"/api/v1/events?projectId={project_b}", headers=headers)
    assert events_b.status_code == 200
    events_rows = events_b.json()["events"]
    assert len(events_rows) == 1
    assert events_rows[0]["project_id"] == project_b

    unauthorized_timeline = client.get(f"/api/v1/snapshots/timeline?projectId={project_a}", headers=headers_other)
    assert unauthorized_timeline.status_code == 403


def test_project_scoped_archaeology_uses_selected_project_only(client: TestClient, monkeypatch) -> None:
    import main

    headers = _signup_headers(client, "e2e-arch")
    project_a = client.post("/api/v1/projects", headers=headers, json={"name": "A"}).json()["id"]
    project_b = client.post("/api/v1/projects", headers=headers, json={"name": "B"}).json()["id"]

    ts = datetime.now(timezone.utc).isoformat()

    async def fake_timeline(limit: int = 800, user_id: str | None = None, project_id: str | None = None):
        rows = [
            {"id": "a", "timestamp": ts, "active_file": "src/service.py", "summary": "A", "project_id": project_a, "git_branch": "main", "terminal_commands": "[]"},
            {"id": "b", "timestamp": ts, "active_file": "src/service.py", "summary": "B", "project_id": project_b, "git_branch": "main", "terminal_commands": "[]"},
        ]
        if project_id:
            return [row for row in rows if row["project_id"] == project_id]
        return rows

    async def fake_semantic_search(query: str, top_k: int = 6, user_id: str | None = None, project_id: str | None = None):
        return await fake_timeline(project_id=project_id)

    observed_project_ids: list[str | None] = []

    async def fake_synthesize(symbol_name: str, commit_message: str, snapshots: list[dict]):
        observed_project_ids.extend(snapshot.get("project_id") for snapshot in snapshots)
        return "ok", ["main"], [], 0.9

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
    assert response.json()["found"] is True
    assert observed_project_ids
    assert set(observed_project_ids) == {project_a}
