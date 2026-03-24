from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth.database import UserDB
from auth.jwt_handler import get_current_principal, get_current_user
from models.schemas import ProjectResolveRequest, ProjectResolveResponse
from projects.database import ProjectDB

logger = logging.getLogger("secondcortex.projects.routes")

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])
project_db = ProjectDB()
user_db = UserDB()


class ProjectCreateRequest(BaseModel):
    name: str
    slug: str | None = None
    visibility: Literal["private", "team"] = "private"
    team_id: str | None = Field(None, alias="teamId")
    workspace_name: str | None = Field(None, alias="workspaceName")
    workspace_path_hash: str | None = Field(None, alias="workspacePathHash")
    repo_remote: str | None = Field(None, alias="repoRemote")

    model_config = {"populate_by_name": True}


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    slug: str | None = None
    visibility: Literal["private", "team"] | None = None
    team_id: str | None = Field(None, alias="teamId")
    workspace_name: str | None = Field(None, alias="workspaceName")
    workspace_path_hash: str | None = Field(None, alias="workspacePathHash")
    repo_remote: str | None = Field(None, alias="repoRemote")

    model_config = {"populate_by_name": True}


class ProjectResponse(BaseModel):
    id: str
    owner_user_id: str
    name: str
    slug: str | None = None
    visibility: Literal["private", "team"]
    team_id: str | None = None
    workspace_name: str | None = None
    workspace_path_hash: str | None = None
    repo_remote: str | None = None
    is_archived: bool
    created_at: int
    updated_at: int


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]


def _resolve_user_team_id(user_id: str) -> str | None:
    user = user_db.get_user_by_id(user_id)
    if not user:
        return None
    return user.get("team_id")


def _normalize_project_response(project: dict) -> ProjectResponse:
    return ProjectResponse(
        id=project["id"],
        owner_user_id=project["owner_user_id"],
        name=project["name"],
        slug=project.get("slug"),
        visibility=project["visibility"],
        team_id=project.get("team_id"),
        workspace_name=project.get("workspace_name"),
        workspace_path_hash=project.get("workspace_path_hash"),
        repo_remote=project.get("repo_remote"),
        is_archived=bool(project.get("is_archived")),
        created_at=int(project.get("created_at") or 0),
        updated_at=int(project.get("updated_at") or 0),
    )


@router.get("", response_model=ProjectListResponse)
async def list_projects(principal: dict = Depends(get_current_principal)):
    role = str(principal.get("role") or "user")

    if role == "pm_guest":
        scopes = principal.get("scopes") or []
        if isinstance(scopes, str):
            scopes = [scopes]
        if "pm:read" not in {str(scope) for scope in scopes}:
            raise HTTPException(status_code=403, detail="PM guest token lacks read scope.")

        team_id = str(principal.get("team_id") or "").strip()
        if not team_id:
            return {"projects": []}

        projects = project_db.list_team_projects(team_id=team_id, include_archived=False)
        return {"projects": [_normalize_project_response(project) for project in projects]}

    user_id = str(principal.get("sub") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload.")

    team_id = _resolve_user_team_id(user_id)
    projects = project_db.list_visible_projects(user_id=user_id, team_id=team_id)
    return {"projects": [_normalize_project_response(project) for project in projects]}


@router.post("", response_model=ProjectResponse)
async def create_project(request: ProjectCreateRequest, user_id: str = Depends(get_current_user)):
    team_id = request.team_id or _resolve_user_team_id(user_id)

    project = project_db.create_project(
        owner_user_id=user_id,
        name=request.name.strip(),
        slug=request.slug,
        visibility=request.visibility,
        team_id=team_id,
        workspace_name=request.workspace_name,
        workspace_path_hash=request.workspace_path_hash,
        repo_remote=request.repo_remote,
    )
    logger.info("Created project %s for user=%s", project["id"], user_id)
    return _normalize_project_response(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, request: ProjectUpdateRequest, user_id: str = Depends(get_current_user)):
    existing = project_db.get_project_by_id(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    if existing["owner_user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Only project owner can update project")

    updates = request.model_dump(by_alias=False, exclude_none=True)
    if not updates:
        return _normalize_project_response(existing)

    if updates.get("visibility") == "team" and not updates.get("team_id") and not existing.get("team_id"):
        updates["team_id"] = _resolve_user_team_id(user_id)

    updated = project_db.update_project(project_id=project_id, owner_user_id=user_id, updates=updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")

    return _normalize_project_response(updated)


@router.post("/{project_id}/archive", response_model=ProjectResponse)
async def archive_project(project_id: str, user_id: str = Depends(get_current_user)):
    existing = project_db.get_project_by_id(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    if existing["owner_user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Only project owner can archive project")

    updated = project_db.set_archived_state(project_id=project_id, owner_user_id=user_id, is_archived=True)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return _normalize_project_response(updated)


@router.post("/{project_id}/unarchive", response_model=ProjectResponse)
async def unarchive_project(project_id: str, user_id: str = Depends(get_current_user)):
    existing = project_db.get_project_by_id(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    if existing["owner_user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Only project owner can unarchive project")

    updated = project_db.set_archived_state(project_id=project_id, owner_user_id=user_id, is_archived=False)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return _normalize_project_response(updated)


@router.delete("/{project_id}")
async def delete_project(project_id: str, user_id: str = Depends(get_current_user)):
    existing = project_db.get_project_by_id(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")
    if existing["owner_user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Only project owner can delete project")

    deleted = project_db.delete_project(project_id=project_id, owner_user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    logger.info("Deleted project %s for user=%s", project_id, user_id)
    return {"status": "deleted", "project_id": project_id}


@router.post("/resolve", response_model=ProjectResolveResponse)
async def resolve_project(request: ProjectResolveRequest, user_id: str = Depends(get_current_user)):
    team_id = request.team_id or _resolve_user_team_id(user_id)
    candidates = project_db.resolve_candidates(
        user_id=user_id,
        team_id=team_id,
        workspace_name=request.workspace_name,
        workspace_path_hash=request.workspace_path_hash,
        repo_remote=request.repo_remote,
    )

    if not candidates:
        logger.info("project resolver status=unresolved user=%s", user_id)
        return ProjectResolveResponse(
            status="unresolved",
            projectId=None,
            confidence=0.0,
            candidates=[],
            needsSelection=True,
        )

    if len(candidates) == 1 and candidates[0]["confidence"] >= 0.9:
        best = candidates[0]
        logger.info("project resolver status=resolved user=%s project=%s", user_id, best["projectId"])
        return ProjectResolveResponse(
            status="resolved",
            projectId=best["projectId"],
            confidence=float(best["confidence"]),
            candidates=candidates[:5],
            needsSelection=False,
        )

    logger.info("project resolver status=ambiguous user=%s candidates=%d", user_id, len(candidates))
    return ProjectResolveResponse(
        status="ambiguous",
        projectId=None,
        confidence=float(candidates[0]["confidence"]),
        candidates=candidates[:5],
        needsSelection=True,
    )
