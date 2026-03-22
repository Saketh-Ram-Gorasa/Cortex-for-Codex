import pytest
import json
from fastapi.testclient import TestClient
import uuid


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    """Create a test user and return auth headers."""
    email = f"test{uuid.uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "test123", "display_name": "Test User"},
    )
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_team(client, auth_headers):
    """Test creating a team as a user."""
    response = client.post(
        "/api/v1/teams",
        headers=auth_headers,
        json={"name": "Backend Squad"},
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Backend Squad"
    assert "team_id" in data
    assert "invite_code" in data


def test_get_team_members(client, auth_headers):
    """Test getting team members."""
    # Create team
    create_resp = client.post(
        "/api/v1/teams",
        headers=auth_headers,
        json={"name": "Test Team"},
    )
    team_id = create_resp.json()["team_id"]
    
    # Get members
    response = client.get(
        f"/api/v1/teams/{team_id}/members",
        headers=auth_headers,
    )
    
    assert response.status_code == 200
    members = response.json()
    assert isinstance(members, list)


def test_join_team_with_code(client, auth_headers):
    """Test joining a team with invite code."""
    # User 1 creates team
    create_resp = client.post(
        "/api/v1/teams",
        headers=auth_headers,
        json={"name": "Test Team"},
    )
    invite_code = create_resp.json()["invite_code"]
    
    # User 2 signs up
    email2 = f"test{uuid.uuid4().hex[:8]}@example.com"
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={"email": email2, "password": "test123", "display_name": "User 2"},
    )
    token2 = signup_resp.json()["token"]
    headers2 = {"Authorization": f"Bearer {token2}"}
    
    # User 2 joins team with code
    response = client.post(
        "/api/v1/teams/join",
        headers=headers2,
        json={"invite_code": invite_code},
    )
    
    assert response.status_code == 200
    assert response.json()["team_id"] is not None
