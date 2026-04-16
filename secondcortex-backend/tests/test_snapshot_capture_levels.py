from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest
from fastapi.testclient import TestClient

from models.schemas import SnapshotPayload


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


def test_snapshot_payload_defaults_capture_level_to_medium() -> None:
    payload = SnapshotPayload(
        timestamp=datetime.now(tz=timezone.utc),
        workspaceFolder="repo",
        activeFile="src/main.py",
        languageId="python",
        shadowGraph="print('hello')",
        terminalCommands=[],
    )

    assert payload.capture_level == "medium"
    assert payload.capture_meta == {}


@pytest.mark.parametrize("level", ["base", "medium", "full", "ultra"])
def test_snapshot_api_accepts_all_capture_levels(client: TestClient, level: str) -> None:
    headers = _signup_headers(client, f"capture-{level}")

    response = client.post(
        "/api/v1/snapshot",
        headers=headers,
        json={
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "workspaceFolder": "repo",
            "activeFile": "src/main.py",
            "languageId": "python",
            "shadowGraph": "print('hello')",
            "terminalCommands": [],
            "captureLevel": level,
            "captureMeta": {
                "includedArtifacts": {
                    "metadata": True,
                }
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_snapshot_payload_rejects_unknown_capture_level() -> None:
    with pytest.raises(Exception):
        SnapshotPayload(
            timestamp=datetime.now(tz=timezone.utc),
            workspaceFolder="repo",
            activeFile="src/main.py",
            languageId="python",
            shadowGraph="print('hello')",
            terminalCommands=[],
            captureLevel="invalid-level",
        )
