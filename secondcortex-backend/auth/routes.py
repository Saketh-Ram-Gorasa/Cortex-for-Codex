"""
Auth API routes: signup, login, me.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel, EmailStr

from auth.database import UserDB
from auth.jwt_handler import create_token, create_pm_guest_token, get_current_principal, get_current_user
from config import settings
from services.vector_db import VectorDBService

logger = logging.getLogger("secondcortex.auth.routes")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Shared DB instance
user_db = UserDB()
vector_db = VectorDBService()


class SignupRequest(BaseModel):
    email: str
    password: str
    display_name: str = ""
    team_id: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user_id: str
    email: str
    display_name: str
    team_id: str | None = None


class MCPKeyResponse(BaseModel):
    api_key: str | None


class MCPKeyIssueRequest(BaseModel):
    name: str = "default"
    scopes: list[str] = ["memory:read"]
    ttl_days: int | None = None


class MCPKeyMetadata(BaseModel):
    key_id: str
    name: str
    scopes: list[str]
    created_at: str | None = None
    expires_at: str | None = None
    last_used_at: str | None = None
    is_revoked: bool


class MCPKeyIssueResponse(BaseModel):
    api_key: str
    key_id: str
    name: str
    scopes: list[str]
    expires_at: str


class MCPKeyListResponse(BaseModel):
    keys: list[MCPKeyMetadata]


class MeResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    team_id: str | None = None


class PMGuestLoginResponse(BaseModel):
    token: str
    role: str
    team_id: str
    display_name: str


class GuestLoginResponse(BaseModel):
    token: str
    role: str
    user_id: str
    email: str
    display_name: str
    team_id: str | None = None


@router.post("/signup", response_model=AuthResponse)
async def signup(req: SignupRequest):
    """Create a new account."""
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    user = user_db.create_user(req.email, req.password, req.display_name, req.team_id)
    if user is None:
        raise HTTPException(status_code=409, detail="An account with that email already exists.")

    token = create_token(user["id"], user["email"])
    logger.info("User signed up: %s", user["email"])

    return AuthResponse(
        token=token,
        user_id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
        team_id=user.get("team_id"),
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    """Log in and get a JWT token."""
    user = user_db.authenticate(req.email, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_token(user["id"], user["email"])
    logger.info("User logged in: %s", user["email"])

    return AuthResponse(
        token=token,
        user_id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
        team_id=user.get("team_id"),
    )


@router.post("/mcp-key", response_model=MCPKeyResponse)
async def generate_mcp_key(
    req: MCPKeyIssueRequest | None = Body(default=None),
    user_id: str = Depends(get_current_user),
):
    """Generate a new MCP API key for the current user (legacy-compatible response)."""
    payload = req or MCPKeyIssueRequest()
    issued = user_db.issue_mcp_api_key(
        user_id=user_id,
        name=payload.name,
        scopes=payload.scopes,
        ttl_days=payload.ttl_days,
    )
    return MCPKeyResponse(api_key=issued["api_key"])


@router.post("/mcp-keys", response_model=MCPKeyIssueResponse)
async def issue_mcp_key(
    req: MCPKeyIssueRequest,
    user_id: str = Depends(get_current_user),
):
    """Issue a named scoped MCP API key with expiration metadata."""
    issued = user_db.issue_mcp_api_key(
        user_id=user_id,
        name=req.name,
        scopes=req.scopes,
        ttl_days=req.ttl_days,
    )
    return MCPKeyIssueResponse(**issued)


@router.get("/mcp-keys", response_model=MCPKeyListResponse)
async def list_mcp_keys(user_id: str = Depends(get_current_user)):
    """List all MCP API keys issued for the current user."""
    keys = user_db.list_mcp_api_keys(user_id)
    return MCPKeyListResponse(keys=[MCPKeyMetadata(**key) for key in keys])


@router.delete("/mcp-keys/{key_id}")
async def revoke_mcp_key(
    key_id: str,
    user_id: str = Depends(get_current_user),
):
    """Revoke one MCP API key by key_id for the current user."""
    revoked = user_db.revoke_mcp_api_key(user_id=user_id, key_id=key_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="MCP key not found")
    return {
        "status": "revoked",
        "key_id": key_id,
        "revoked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


@router.get("/mcp-key", response_model=MCPKeyResponse)
async def get_mcp_key(user_id: str = Depends(get_current_user)):
    """Get the current user's existing MCP API key."""
    api_key = user_db.get_mcp_api_key(user_id)
    return MCPKeyResponse(api_key=api_key)


@router.post("/pm-guest/login", response_model=PMGuestLoginResponse)
async def pm_guest_login():
    """Issue a restricted PM guest token (read/chat scope only)."""
    if not settings.pm_guest_enabled:
        raise HTTPException(status_code=403, detail="PM guest login is disabled.")

    configured_team_id = (settings.pm_guest_team_id or "").strip()
    candidate_team_ids: list[str] = []
    if configured_team_id:
        candidate_team_ids.append(configured_team_id)

    inferred_team_id = user_db.get_most_active_team_id()
    if inferred_team_id and inferred_team_id not in candidate_team_ids:
        candidate_team_ids.append(inferred_team_id)

    if not candidate_team_ids:
        raise HTTPException(status_code=503, detail="PM guest login is unavailable: no team is configured.")

    resolved_team_id: str | None = None
    fallback_team_id: str | None = None
    for candidate in candidate_team_ids:
        team_info = user_db.get_team_info(candidate)
        if not team_info:
            continue

        members = user_db.get_team_members(candidate)
        if not members:
            continue

        # Keep a fallback in case snapshot stores are temporarily unavailable.
        if fallback_team_id is None:
            fallback_team_id = candidate

        # Prefer teams where at least one member has snapshot history.
        has_snapshot_activity = False
        for member in members:
            member_id = str(member.get("id") or "").strip()
            if not member_id:
                continue

            timeline = await vector_db.get_snapshot_timeline(limit=1, user_id=member_id)
            if timeline:
                has_snapshot_activity = True
                break

            legacy_rows = user_db.get_user_snapshots(member_id, limit=1)
            if legacy_rows:
                has_snapshot_activity = True
                break

        if has_snapshot_activity:
            resolved_team_id = candidate
            break

    if not resolved_team_id and fallback_team_id:
        resolved_team_id = fallback_team_id

    if not resolved_team_id:
        raise HTTPException(status_code=503, detail="PM guest login is unavailable: no active team data found.")

    display_name = (settings.pm_guest_display_name or "PM Guest").strip()
    token = create_pm_guest_token(team_id=resolved_team_id, display_name=display_name)

    return PMGuestLoginResponse(
        token=token,
        role="pm_guest",
        team_id=resolved_team_id,
        display_name=display_name,
    )


@router.post("/guest/login", response_model=GuestLoginResponse)
async def guest_login():
    """Issue a credentialless developer guest token mapped to an existing snapshot-rich user."""
    preferred_email = os.getenv("DEV_GUEST_EMAIL", "").strip().lower()

    user = user_db.get_user_by_email(preferred_email) if preferred_email else None
    if not user:
        user = user_db.get_most_active_user()

    if not user:
        fallback_email = "guest@secondcortex.local"
        fallback_password = f"guest-{(settings.jwt_secret or 'dev-secret')[:12]}"
        fallback_display = "Guest Developer"

        created = user_db.create_user(fallback_email, fallback_password, fallback_display)
        if created:
            user = created
        else:
            user = user_db.get_user_by_email(fallback_email)

    if not user:
        raise HTTPException(status_code=503, detail="Guest login unavailable. No user context is configured.")

    token = create_token(user["id"], user["email"])
    logger.info("Guest developer login mapped to user: %s", user["email"])

    return GuestLoginResponse(
        token=token,
        role="developer_guest",
        user_id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
        team_id=user.get("team_id"),
    )


@router.get("/me", response_model=MeResponse)
async def get_me(principal: dict = Depends(get_current_principal)):
    """Return current authenticated principal metadata."""
    role = str(principal.get("role") or "user")
    if role == "pm_guest":
        team_id = str(principal.get("team_id") or "").strip() or None
        return MeResponse(
            user_id=str(principal.get("sub") or "pm_guest"),
            email=str(principal.get("email") or settings.pm_guest_email),
            display_name=str(principal.get("display_name") or settings.pm_guest_display_name),
            team_id=team_id,
        )

    user_id = str(principal.get("sub") or "")
    user = user_db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return MeResponse(
        user_id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
        team_id=user.get("team_id"),
    )
