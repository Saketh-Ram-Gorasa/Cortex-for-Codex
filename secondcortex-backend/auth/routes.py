"""
Auth API routes: signup, login, me.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr

from auth.database import UserDB
from auth.jwt_handler import create_token, create_pm_guest_token, get_current_principal, get_current_user
from config import settings

logger = logging.getLogger("secondcortex.auth.routes")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Shared DB instance
user_db = UserDB()


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
async def generate_mcp_key(user_id: str = Depends(get_current_user)):
    """Generate a new MCP API key for the current user."""
    new_key = user_db.generate_mcp_api_key(user_id)
    return MCPKeyResponse(api_key=new_key)


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

    team_id = (settings.pm_guest_team_id or "").strip()
    if not team_id:
        raise HTTPException(status_code=503, detail="PM_GUEST_TEAM_ID is not configured.")

    team_info = user_db.get_team_info(team_id)
    if not team_info:
        raise HTTPException(status_code=503, detail="Configured PM guest team does not exist.")

    display_name = (settings.pm_guest_display_name or "PM Guest").strip()
    token = create_pm_guest_token(team_id=team_id, display_name=display_name)

    return PMGuestLoginResponse(
        token=token,
        role="pm_guest",
        team_id=team_id,
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
