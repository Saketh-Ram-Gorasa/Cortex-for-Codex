import pytest
from auth.database import UserDB
import uuid


def test_create_team():
    """Test creating a new team."""
    db = UserDB()
    team_id = str(uuid.uuid4())
    team_name = "Backend Squad"
    team_lead_id = str(uuid.uuid4())
    
    # Create the team lead user first
    db.create_user(f"lead{uuid.uuid4().hex[:4]}@test.com", "pass123", "Team Lead", None)
    user = db.get_user_by_id(team_lead_id)
    if not user:
        # If get by id doesn't work, use first user created
        team_lead_user = db.create_user(f"lead{uuid.uuid4().hex[:4]}@test.com", "pass123", "Team Lead")
        if team_lead_user:
            team_lead_id = team_lead_user["id"]
    
    team = db.create_team(team_id, team_name, team_lead_id)
    
    assert team is not None
    assert team["id"] == team_id
    assert team["name"] == team_name
    assert team["team_lead_id"] == team_lead_id


def test_generate_invite_code():
    """Test generating an invite code for a team."""
    db = UserDB()
    team_id = str(uuid.uuid4())
    
    # Create team lead user
    team_lead_user = db.create_user(f"lead{uuid.uuid4().hex[:4]}@test.com", "pass123", "Team Lead")
    team_lead_id = team_lead_user["id"]
    
    # Create team
    db.create_team(team_id, "Test Team", team_lead_id)
    
    # Generate code
    code = db.generate_invite_code(team_id, team_lead_id)
    
    assert code is not None
    assert isinstance(code, str)
    assert len(code) == 8  # 8-char alphanumeric


def test_join_team_with_invite_code():
    """Test joining a team using an invite code."""
    db = UserDB()
    team_id = str(uuid.uuid4())
    
    # Create team lead user
    team_lead_user = db.create_user(f"lead{uuid.uuid4().hex[:4]}@test.com", "pass123", "Team Lead")
    team_lead_id = team_lead_user["id"]
    
    # Create member user
    member_user = db.create_user(f"member{uuid.uuid4().hex[:4]}@test.com", "pass123", "Team Member")
    user_id = member_user["id"]
    
    # Create team and generate code
    db.create_team(team_id, "Test Team", team_lead_id)
    code = db.generate_invite_code(team_id, team_lead_id)
    
    # Join team with code
    result = db.join_team_with_code(user_id, code)
    
    assert result is True
    user = db.get_user_by_id(user_id)
    assert user["team_id"] == team_id


def test_get_team_members():
    """Test getting all members of a team."""
    db = UserDB()
    team_id = str(uuid.uuid4())
    
    # Create team lead user
    team_lead_user = db.create_user(f"lead{uuid.uuid4().hex[:4]}@test.com", "pass123", "Team Lead")
    team_lead_id = team_lead_user["id"]
    
    # Create member users
    member_user1 = db.create_user(f"member1{uuid.uuid4().hex[:4]}@test.com", "pass123", "Member 1")
    user1_id = member_user1["id"]
    
    member_user2 = db.create_user(f"member2{uuid.uuid4().hex[:4]}@test.com", "pass123", "Member 2")
    user2_id = member_user2["id"]
    
    # Create team
    db.create_team(team_id, "Test Team", team_lead_id)
    code = db.generate_invite_code(team_id, team_lead_id)
    
    # Have members join
    db.join_team_with_code(user1_id, code)
    
    # Generate new code for second member (codes are one-use)
    code2 = db.generate_invite_code(team_id, team_lead_id)
    db.join_team_with_code(user2_id, code2)
    
    members = db.get_team_members(team_id)
    
    assert len(members) == 3
    assert team_lead_id in [m["id"] for m in members]
    assert user1_id in [m["id"] for m in members]
    assert user2_id in [m["id"] for m in members]
