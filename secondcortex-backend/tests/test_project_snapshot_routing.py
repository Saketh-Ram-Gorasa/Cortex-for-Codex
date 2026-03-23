from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import uuid

import pytest
from fastapi.testclient import TestClient

from agents.retriever import RetrieverAgent
from models.schemas import MemoryMetadata, MemoryOperation, SnapshotPayload


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


def test_retriever_and_vectordb_receive_project_id() -> None:
    class FakeVectorDB:
        def __init__(self) -> None:
            self.received_project_id: str | None = None

        async def generate_embedding(self, text: str) -> list[float]:
            return [0.1, 0.2, 0.3]

        async def upsert_snapshot(self, snapshot, user_id: str | None = None) -> None:
            self.received_project_id = snapshot.project_id

    vector = FakeVectorDB()
    retriever = RetrieverAgent(vector)

    async def _force_add(*args, **kwargs):
        return MemoryMetadata(operation=MemoryOperation.ADD, summary="test add")

    retriever._route_operation = _force_add

    payload = SnapshotPayload(
        timestamp=datetime.now(tz=timezone.utc),
        workspaceFolder="repo",
        activeFile="main.py",
        languageId="python",
        shadowGraph="def fn(): pass",
        terminalCommands=["pytest -q"],
        projectId="proj-123",
    )

    stored = asyncio.run(retriever.process_snapshot(payload, user_id="u1"))

    assert stored.project_id == "proj-123"
    assert vector.received_project_id == "proj-123"


def test_snapshot_rejected_without_project_id_when_project_mode_enabled(client: TestClient, monkeypatch) -> None:
    import main

    headers = _signup_headers(client, "proj-mode")
    monkeypatch.setattr(main.settings, "project_scoped_ingestion_enabled", True)

    response = client.post(
        "/api/v1/snapshot",
        headers=headers,
        json={
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "workspaceFolder": "repo",
            "activeFile": "app.py",
            "languageId": "python",
            "shadowGraph": "print('hi')",
            "terminalCommands": [],
        },
    )

    assert response.status_code == 400
    assert "projectId" in response.json()["detail"]
