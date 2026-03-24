import pytest
from fastapi.testclient import TestClient
import uuid


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


@pytest.fixture
def team_setup(client):
    """Create a team and return team_id, auth headers."""
    # Create user
    email = f"test{uuid.uuid4().hex[:8]}@example.com"
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "test123", "display_name": "Test User"},
    )
    token = signup_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create team
    team_resp = client.post(
        "/api/v1/teams",
        headers=headers,
        json={"name": "Test Team"},
    )
    team_id = team_resp.json()["team_id"]
    
    yield {"team_id": team_id, "headers": headers}


def test_get_daily_summary(client, team_setup):
    """Test getting daily team summary."""
    team_id = team_setup["team_id"]
    headers = team_setup["headers"]
    
    response = client.get(
        f"/api/v1/summaries/team/{team_id}/daily",
        headers=headers,
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["team_id"] == team_id
    assert data["period"] == "daily"
    assert "members" in data
    assert "generated_at" in data


def test_get_weekly_summary(client, team_setup):
    """Test getting weekly team summary."""
    team_id = team_setup["team_id"]
    headers = team_setup["headers"]
    
    response = client.get(
        f"/api/v1/summaries/team/{team_id}/weekly",
        headers=headers,
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["team_id"] == team_id
    assert data["period"] == "weekly"
    assert "members" in data
    assert "daily_breakdown" in data


def test_get_team_evolution_summary_daily(client, team_setup):
    """Team evolution endpoint returns compressed daily feed shape."""
    team_id = team_setup["team_id"]
    headers = team_setup["headers"]

    response = client.get(
        f"/api/v1/summaries/team/{team_id}/evolution?mode=daily&limit=20",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["team_id"] == team_id
    assert data["mode"] == "daily"
    assert "snapshot_count" in data
    assert "entries" in data
    assert isinstance(data["entries"], list)


def test_get_team_evolution_summary_feature(client, team_setup):
    """Team evolution endpoint returns compressed feature feed shape."""
    team_id = team_setup["team_id"]
    headers = team_setup["headers"]

    response = client.get(
        f"/api/v1/summaries/team/{team_id}/evolution?mode=feature&limit=20",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["team_id"] == team_id
    assert data["mode"] == "feature"
    assert "snapshot_count" in data
    assert "entries" in data
    assert isinstance(data["entries"], list)
