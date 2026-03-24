from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import auth.routes as auth_routes


@pytest.mark.parametrize("configured_team_id,inferred_team_id,expected_team", [("team-a", "team-b", "team-a"), ("", "team-b", "team-b")])
def test_pm_guest_login_resolves_first_valid_team_fast(monkeypatch, configured_team_id: str, inferred_team_id: str, expected_team: str):
    calls = {"get_user_snapshots": 0, "create_task": 0}

    monkeypatch.setattr(auth_routes.settings, "pm_guest_enabled", True)
    monkeypatch.setattr(auth_routes.settings, "pm_guest_team_id", configured_team_id)
    monkeypatch.setattr(auth_routes.settings, "pm_guest_display_name", "PM Guest")

    monkeypatch.setattr(auth_routes.user_db, "get_most_active_team_id", lambda: inferred_team_id)
    monkeypatch.setattr(auth_routes.user_db, "get_team_info", lambda team_id: {"id": team_id})
    monkeypatch.setattr(auth_routes.user_db, "get_team_members", lambda team_id: [{"id": "u-1"}])

    def fake_get_user_snapshots(user_id: str, limit: int = 1):
        calls["get_user_snapshots"] += 1
        return []

    monkeypatch.setattr(auth_routes.user_db, "get_user_snapshots", fake_get_user_snapshots)
    monkeypatch.setattr(auth_routes, "create_pm_guest_token", lambda team_id, display_name=None: f"token-{team_id}")

    async def fake_bootstrap(team_id: str) -> None:
        return None

    monkeypatch.setattr(auth_routes, "_bootstrap_secondcortex_project_safe", fake_bootstrap)

    def fake_create_task(coro):
        calls["create_task"] += 1
        coro.close()
        return None

    monkeypatch.setattr(auth_routes.asyncio, "create_task", fake_create_task)

    response = asyncio.run(auth_routes.pm_guest_login())

    assert response.team_id == expected_team
    assert response.token == f"token-{expected_team}"
    assert calls["get_user_snapshots"] == 0
    assert calls["create_task"] == 1


def test_pm_guest_login_returns_503_when_no_valid_team(monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "pm_guest_enabled", True)
    monkeypatch.setattr(auth_routes.settings, "pm_guest_team_id", "")
    monkeypatch.setattr(auth_routes.user_db, "get_most_active_team_id", lambda: None)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_routes.pm_guest_login())

    assert exc.value.status_code == 503
    assert "no team is configured" in str(exc.value.detail).lower()
