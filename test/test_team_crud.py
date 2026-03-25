"""
Full CRUD test suite for Team management.
Tests: create, join, list members, rename, delete, leave, remove member, auth edge cases.
"""

from __future__ import annotations

from conftest import signup, create_team

#just a sanity check to ensure test setup is working

def test_create_team(client):
    """Create a team and verify response includes invite code."""
    user = signup(client, "team-create")
    team = create_team(client, user["headers"], "SquadAlpha")

    assert team["name"] == "SquadAlpha"
    assert "team_id" in team
    assert "invite_code" in team
    assert len(team["invite_code"]) == 8


def test_join_team_with_invite_code(client):
    """Join a team using an invite code."""
    lead = signup(client, "team-lead")
    member = signup(client, "team-member")
    team = create_team(client, lead["headers"], "JoinTest")

    resp = client.post(
        "/api/v1/teams/join",
        headers=member["headers"],
        json={"invite_code": team["invite_code"]},
    )
    assert resp.status_code == 200
    assert resp.json()["team_id"] == team["team_id"]


def test_join_team_invalid_code_400(client):
    """Joining with an invalid invite code returns 400."""
    user = signup(client, "team-bad-code")
    resp = client.post(
        "/api/v1/teams/join",
        headers=user["headers"],
        json={"invite_code": "BADCODE1"},
    )
    assert resp.status_code == 400


def test_get_team_members(client):
    """Get all members of a team after joining."""
    lead = signup(client, "team-lead-m")
    member = signup(client, "team-member-m")
    team = create_team(client, lead["headers"], "MembersTest")

    client.post(
        "/api/v1/teams/join",
        headers=member["headers"],
        json={"invite_code": team["invite_code"]},
    )

    resp = client.get(
        f"/api/v1/teams/{team['team_id']}/members",
        headers=lead["headers"],
    )
    assert resp.status_code == 200
    members = resp.json()
    ids = [m["id"] for m in members]
    assert lead["user_id"] in ids
    assert member["user_id"] in ids


def test_get_my_teams(client):
    """Get all teams the current user belongs to."""
    user = signup(client, "team-mine")
    create_team(client, user["headers"], "MyTeamA")
    create_team(client, user["headers"], "MyTeamB")

    resp = client.get("/api/v1/teams/mine", headers=user["headers"])
    assert resp.status_code == 200
    teams = resp.json()
    names = {t["name"] for t in teams}
    assert "MyTeamA" in names
    assert "MyTeamB" in names


def test_rename_team(client):
    """Team lead can rename a team."""
    lead = signup(client, "team-rename-lead")
    team = create_team(client, lead["headers"], "OldTeamName")

    resp = client.patch(
        f"/api/v1/teams/{team['team_id']}",
        headers=lead["headers"],
        json={"name": "NewTeamName"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "NewTeamName"


def test_rename_team_403_for_non_lead(client):
    """Non-lead cannot rename a team."""
    lead = signup(client, "team-rename-l")
    member = signup(client, "team-rename-m")
    team = create_team(client, lead["headers"], "LeadOnlyRename")

    client.post(
        "/api/v1/teams/join",
        headers=member["headers"],
        json={"invite_code": team["invite_code"]},
    )

    resp = client.patch(
        f"/api/v1/teams/{team['team_id']}",
        headers=member["headers"],
        json={"name": "Hacked"},
    )
    assert resp.status_code == 403


def test_delete_team(client):
    """Team lead can delete a team."""
    lead = signup(client, "team-del-lead")
    team = create_team(client, lead["headers"], "Doomed")

    resp = client.delete(
        f"/api/v1/teams/{team['team_id']}",
        headers=lead["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    # Verify it's gone from listing
    listing = client.get("/api/v1/teams/mine", headers=lead["headers"])
    assert listing.status_code == 200
    team_ids = [t["id"] for t in listing.json()]
    assert team["team_id"] not in team_ids


def test_delete_team_403_for_non_lead(client):
    """Non-lead cannot delete a team."""
    lead = signup(client, "team-del-l")
    member = signup(client, "team-del-m")
    team = create_team(client, lead["headers"], "Protected")

    client.post(
        "/api/v1/teams/join",
        headers=member["headers"],
        json={"invite_code": team["invite_code"]},
    )

    resp = client.delete(
        f"/api/v1/teams/{team['team_id']}",
        headers=member["headers"],
    )
    assert resp.status_code == 403


def test_leave_team(client):
    """A member can leave a team."""
    lead = signup(client, "team-leave-l")
    member = signup(client, "team-leave-m")
    team = create_team(client, lead["headers"], "LeaveTest")

    client.post(
        "/api/v1/teams/join",
        headers=member["headers"],
        json={"invite_code": team["invite_code"]},
    )

    resp = client.post(
        f"/api/v1/teams/{team['team_id']}/leave",
        headers=member["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "left"

    # Verify member is no longer listed
    members_resp = client.get(
        f"/api/v1/teams/{team['team_id']}/members",
        headers=lead["headers"],
    )
    member_ids = [m["id"] for m in members_resp.json()]
    assert member["user_id"] not in member_ids


def test_leave_team_lead_cannot_leave(client):
    """Team lead cannot leave their own team — must delete instead."""
    lead = signup(client, "team-leave-lead")
    team = create_team(client, lead["headers"], "LeadStay")

    resp = client.post(
        f"/api/v1/teams/{team['team_id']}/leave",
        headers=lead["headers"],
    )
    assert resp.status_code == 400


def test_remove_member(client):
    """Team lead can remove a member from the team."""
    lead = signup(client, "team-rm-l")
    member = signup(client, "team-rm-m")
    team = create_team(client, lead["headers"], "RemoveTest")

    client.post(
        "/api/v1/teams/join",
        headers=member["headers"],
        json={"invite_code": team["invite_code"]},
    )

    resp = client.delete(
        f"/api/v1/teams/{team['team_id']}/members/{member['user_id']}",
        headers=lead["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "removed"

    # Verify member is gone
    members_resp = client.get(
        f"/api/v1/teams/{team['team_id']}/members",
        headers=lead["headers"],
    )
    member_ids = [m["id"] for m in members_resp.json()]
    assert member["user_id"] not in member_ids


def test_remove_member_403_for_non_lead(client):
    """Non-lead cannot remove members."""
    lead = signup(client, "team-rm-l2")
    member1 = signup(client, "team-rm-m1")
    member2 = signup(client, "team-rm-m2")
    team = create_team(client, lead["headers"], "RmAuthTest")

    client.post(
        "/api/v1/teams/join",
        headers=member1["headers"],
        json={"invite_code": team["invite_code"]},
    )
    code2 = client.post(
        f"/api/v1/teams/{team['team_id']}/invite-code",
        headers=lead["headers"],
    ).json()["invite_code"]
    client.post(
        "/api/v1/teams/join",
        headers=member2["headers"],
        json={"invite_code": code2},
    )

    resp = client.delete(
        f"/api/v1/teams/{team['team_id']}/members/{member2['user_id']}",
        headers=member1["headers"],
    )
    assert resp.status_code == 403
