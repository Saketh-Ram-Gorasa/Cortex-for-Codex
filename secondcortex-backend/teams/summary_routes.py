"""
Team summary API routes: daily/weekly summaries, pluggable for multiple dashboards.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Depends

from auth.database import UserDB
from auth.jwt_handler import get_current_principal, get_current_user
from services.summary_service import SummaryService

logger = logging.getLogger("secondcortex.teams.summary_routes")

router = APIRouter(prefix="/api/v1/summaries", tags=["summaries"])
user_db = UserDB()
summary_service = SummaryService()


def _authorize_team_summary_read(team_id: str, principal: dict) -> None:
    """Allow team summary read for same-team users or restricted pm_guest tokens."""
    role = str(principal.get("role") or "user")
    if role == "pm_guest":
        scopes = principal.get("scopes") or []
        if isinstance(scopes, str):
            scopes = [scopes]
        if "pm:read" not in set(str(scope) for scope in scopes):
            raise HTTPException(status_code=403, detail="PM guest token lacks read scope.")
        guest_team_id = str(principal.get("team_id") or "")
        if guest_team_id != team_id:
            raise HTTPException(status_code=403, detail="PM guest token is not authorized for this team.")
        return

    user_id = str(principal.get("sub") or "")
    user = user_db.get_user_by_id(user_id)
    if not user or user.get("team_id") != team_id:
        raise HTTPException(status_code=403, detail="You are not a member of this team")


@router.get("/team/{team_id}/daily")
async def get_team_daily_summary(team_id: str, principal: dict = Depends(get_current_principal)):
    """
    Get daily summary for a team.
    User must be a member of the team.
    Pluggable format for team dashboard, PM dashboard, etc.
    """
    _authorize_team_summary_read(team_id, principal)
    summary = summary_service.generate_daily_summary(team_id)
    return summary


@router.get("/team/{team_id}/weekly")
async def get_team_weekly_summary(team_id: str, principal: dict = Depends(get_current_principal)):
    """
    Get weekly summary for a team.
    User must be a member of the team.
    Pluggable format for team dashboard, PM dashboard, etc.
    """
    _authorize_team_summary_read(team_id, principal)
    summary = summary_service.generate_weekly_summary(team_id)
    return summary


@router.get("/user/{user_id}/daily")
async def get_user_daily_summary(user_id: str, current_user: str = Depends(get_current_user)):
    """
    Get daily summary for an individual user.
    User can only fetch their own summary or team leads can fetch team members.
    """
    if user_id != current_user:
        # Check if current user is a team lead of the user's team
        user_data = user_db.get_user_by_id(user_id)
        current_user_data = user_db.get_user_by_id(current_user)
        
        if not user_data or not current_user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_team = user_data.get("team_id")
        current_user_team = current_user_data.get("team_id")
        
        if user_team != current_user_team or not user_team:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        team_info = user_db.get_team_info(user_team)
        if team_info["team_lead_id"] != current_user:
            raise HTTPException(status_code=403, detail="Only team lead can view member summaries")
    
    summary = summary_service.generate_user_daily_summary(user_id)
    return summary


@router.get("/user/{user_id}/weekly")
async def get_user_weekly_summary(user_id: str, current_user: str = Depends(get_current_user)):
    """
    Get weekly summary for an individual user.
    User can only fetch their own summary.
    """
    if user_id != current_user:
        raise HTTPException(status_code=403, detail="You can only view your own summary")
    
    summary = summary_service.generate_user_weekly_summary(user_id)
    return summary
