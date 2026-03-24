"""
Team summary API routes: daily/weekly summaries, pluggable for multiple dashboards.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
import re
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Depends

from auth.database import UserDB
from auth.jwt_handler import get_current_principal, get_current_user
from services.summary_service import SummaryService
from services.vector_db import VectorDBService
from projects.routes import project_db

logger = logging.getLogger("secondcortex.teams.summary_routes")

router = APIRouter(prefix="/api/v1/summaries", tags=["summaries"])
user_db = UserDB()
summary_service = SummaryService()
vector_db = VectorDBService()


def _principal_scopes(principal: dict) -> set[str]:
    scopes = principal.get("scopes") or []
    if isinstance(scopes, str):
        scopes = [scopes]
    return {str(scope) for scope in scopes}


def _parse_snapshot_epoch_seconds(value: object) -> int:
    if isinstance(value, (int, float)):
        numeric = int(value)
        return numeric // 1000 if numeric > 1_000_000_000_000 else numeric

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return 0
        try:
            numeric = int(float(raw))
            return numeric // 1000 if numeric > 1_000_000_000_000 else numeric
        except Exception:
            pass
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp())
        except Exception:
            return 0

    return 0


def _compact_text(value: object, fallback: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    return re.sub(r"\s+", " ", raw)


def _feature_key(active_file: str | None, git_branch: str | None) -> str:
    path = str(active_file or "").replace("\\", "/").strip("/")
    if path:
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2:
            return parts[0]
        leaf = parts[-1]
        if "." in leaf:
            return leaf.rsplit(".", 1)[0]
        return leaf
    branch = str(git_branch or "").strip()
    if branch:
        return branch
    return "general"


def _author_name(member_map: dict[str, dict], user_id: str) -> str:
    member = member_map.get(user_id) or {}
    display_name = str(member.get("display_name") or "").strip()
    if display_name:
        return display_name
    email = str(member.get("email") or "").strip()
    if "@" in email:
        return email.split("@", 1)[0]
    return user_id


def _summarize_daily_group(group_rows: list[dict], member_map: dict[str, dict]) -> tuple[str, list[str]]:
    # Keep this concise for UI cards while preserving both members' contributions.
    by_member: dict[str, list[str]] = defaultdict(list)
    for row in group_rows:
        user_id = str(row.get("user_id") or "")
        summary = _compact_text(row.get("summary"), "No summary")
        if summary not in by_member[user_id]:
            by_member[user_id].append(summary)

    member_names: list[str] = []
    chunks: list[str] = []
    for user_id, summaries in by_member.items():
        name = _author_name(member_map, user_id)
        member_names.append(name)
        chunks.append(f"{name}: {' | '.join(summaries[:2])}")

    return "\n".join(chunks[:4]), member_names


def _summarize_feature_group(group_rows: list[dict], member_map: dict[str, dict]) -> tuple[str, list[str]]:
    by_member: dict[str, list[str]] = defaultdict(list)
    for row in group_rows:
        user_id = str(row.get("user_id") or "")
        summary = _compact_text(row.get("summary"), "No summary")
        if summary not in by_member[user_id]:
            by_member[user_id].append(summary)

    member_names: list[str] = []
    lines: list[str] = []
    for user_id, summaries in by_member.items():
        name = _author_name(member_map, user_id)
        member_names.append(name)
        lines.append(f"{name}: {' | '.join(summaries[:2])}")

    return "\n".join(lines[:4]), member_names


def _authorize_project_scope(principal: dict, project_id: str | None) -> None:
    if not project_id:
        return

    role = str(principal.get("role") or "user")
    if role == "pm_guest":
        scopes = _principal_scopes(principal)
        if "pm:read" not in scopes:
            raise HTTPException(status_code=403, detail="PM guest token lacks read scope.")

        guest_team_id = str(principal.get("team_id") or "")
        project = project_db.get_project_by_id(project_id)
        if not project or project.get("visibility") != "team" or project.get("team_id") != guest_team_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this project")
        return

    requester_user_id = str(principal.get("sub") or "")
    requester = user_db.get_user_by_id(requester_user_id) if requester_user_id else None
    requester_team_id = requester.get("team_id") if requester else None
    if not project_db.user_can_access_project(
        user_id=requester_user_id,
        team_id=requester_team_id,
        project_id=project_id,
    ):
        raise HTTPException(status_code=403, detail="Not authorized to access this project")


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
    if not user_db.is_user_in_team(user_id, team_id):
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


@router.get("/team/{team_id}/evolution")
async def get_team_evolution_summary(
    team_id: str,
    mode: str = "daily",
    limit: int = 120,
    projectId: str | None = None,
    principal: dict = Depends(get_current_principal),
):
    """
    Return a compressed, latest-first Team Cortex timeline.
    Modes:
      - daily: one card per day summarizing all members' snapshots
      - feature: one card per feature bucket summarizing cross-member work
    """
    _authorize_team_summary_read(team_id, principal)
    _authorize_project_scope(principal, projectId)

    normalized_mode = (mode or "daily").strip().lower()
    if normalized_mode not in {"daily", "feature"}:
        raise HTTPException(status_code=400, detail="mode must be one of: daily, feature")

    capped_limit = max(1, min(limit, 300))

    members = user_db.get_team_members(team_id)
    member_map = {str(member.get("id") or ""): member for member in members}
    member_ids = [member_id for member_id in member_map.keys() if member_id]

    if not member_ids:
        return {
            "team_id": team_id,
            "project_id": projectId,
            "mode": normalized_mode,
            "snapshot_count": 0,
            "member_count": 0,
            "entries": [],
        }

    merged_rows: list[dict] = []
    for member_id in member_ids:
        member_rows = await vector_db.get_snapshot_timeline(
            limit=1000,
            user_id=member_id,
            project_id=projectId,
        )
        for row in member_rows:
            enriched = dict(row)
            enriched["user_id"] = member_id
            merged_rows.append(enriched)

    # If project-filtered timelines are empty, fall back to all timelines so PMs still see evolution.
    used_project_filter = bool(projectId)
    if projectId and not merged_rows:
        used_project_filter = False
        for member_id in member_ids:
            member_rows = await vector_db.get_snapshot_timeline(
                limit=1000,
                user_id=member_id,
                project_id=None,
            )
            for row in member_rows:
                enriched = dict(row)
                enriched["user_id"] = member_id
                merged_rows.append(enriched)

    if not merged_rows:
        return {
            "team_id": team_id,
            "project_id": projectId,
            "mode": normalized_mode,
            "snapshot_count": 0,
            "member_count": len(member_ids),
            "used_project_filter": used_project_filter,
            "entries": [],
        }

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in merged_rows:
        ts = _parse_snapshot_epoch_seconds(row.get("timestamp"))
        user_id = str(row.get("user_id") or "")
        if normalized_mode == "daily":
            day = datetime.fromtimestamp(max(ts, 0), tz=timezone.utc).strftime("%Y-%m-%d")
            key = day
        else:
            key = _feature_key(row.get("active_file"), row.get("git_branch"))

        groups[key].append({
            "timestamp": ts,
            "summary": row.get("summary"),
            "active_file": row.get("active_file"),
            "git_branch": row.get("git_branch"),
            "user_id": user_id,
        })

    entries: list[dict] = []
    for key, rows in groups.items():
        if not rows:
            continue
        rows.sort(key=lambda item: int(item.get("timestamp") or 0), reverse=True)
        latest_ts = int(rows[0].get("timestamp") or 0)

        if normalized_mode == "daily":
            summary, member_names = _summarize_daily_group(rows, member_map)
            label = key
            tag = "daily"
        else:
            summary, member_names = _summarize_feature_group(rows, member_map)
            label = key
            tag = "feature"

        entries.append(
            {
                "id": f"{normalized_mode}:{key}",
                "title": label,
                "summary": summary,
                "timestamp": latest_ts,
                "snapshot_count": len(rows),
                "member_names": member_names,
                "tag": tag,
            }
        )

    entries.sort(key=lambda item: int(item.get("timestamp") or 0), reverse=True)
    entries = entries[:capped_limit]

    return {
        "team_id": team_id,
        "project_id": projectId,
        "mode": normalized_mode,
        "snapshot_count": len(merged_rows),
        "member_count": len(member_ids),
        "used_project_filter": used_project_filter,
        "entries": entries,
    }
