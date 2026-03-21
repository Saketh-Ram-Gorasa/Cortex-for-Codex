import pytest
from datetime import datetime, timedelta
from services.summary_service import SummaryService
from auth.database import UserDB
import uuid


@pytest.fixture
def setup():
    """Create test users in a team."""
    db = UserDB()
    
    # Create team lead
    team_lead_user = db.create_user(f"lead{uuid.uuid4().hex[:4]}@test.com", "pass123", "Team Lead")
    team_lead_id = team_lead_user["id"]
    
    # Create team
    team_id = str(uuid.uuid4())
    db.create_team(team_id, "Test Team", team_lead_id)
    
    # Create 2 member users
    user1 = db.create_user(f"member1{uuid.uuid4().hex[:4]}@test.com", "pass123", "Member 1")
    user2 = db.create_user(f"member2{uuid.uuid4().hex[:4]}@test.com", "pass123", "Member 2")
    
    # Add members to team
    code = db.generate_invite_code(team_id, team_lead_id)
    db.join_team_with_code(user1["id"], code)
    
    code2 = db.generate_invite_code(team_id, team_lead_id)
    db.join_team_with_code(user2["id"], code2)
    
    yield {"team_id": team_id, "user1_id": user1["id"], "user2_id": user2["id"], "db": db}


def test_generate_daily_team_summary(setup):
    """Test generating a daily team summary."""
    service = SummaryService()
    team_id = setup["team_id"]
    
    summary = service.generate_daily_summary(team_id)
    
    assert summary is not None
    assert summary["team_id"] == team_id
    assert summary["period"] == "daily"
    assert "members" in summary
    assert "generated_at" in summary
    assert "total_snapshots" in summary
    assert "active_members" in summary


def test_generate_weekly_team_summary(setup):
    """Test generating a weekly team summary."""
    service = SummaryService()
    team_id = setup["team_id"]
    
    summary = service.generate_weekly_summary(team_id)
    
    assert summary is not None
    assert summary["team_id"] == team_id
    assert summary["period"] == "weekly"
    assert "members" in summary
    assert "generated_at" in summary
    assert "daily_breakdown" in summary
