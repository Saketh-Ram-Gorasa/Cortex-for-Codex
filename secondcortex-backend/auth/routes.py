"""
Auth API routes: signup, login, me.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from auth.database import UserDB
from auth.jwt_handler import create_token

logger = logging.getLogger("secondcortex.auth.routes")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Shared DB instance
user_db = UserDB()


class SignupRequest(BaseModel):
    email: str
    password: str
    display_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user_id: str
    email: str
    display_name: str


@router.post("/signup", response_model=AuthResponse)
async def signup(req: SignupRequest):
    """Create a new account."""
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    user = user_db.create_user(req.email, req.password, req.display_name)
    if user is None:
        raise HTTPException(status_code=409, detail="An account with that email already exists.")

    token = create_token(user["id"], user["email"])
    logger.info("User signed up: %s", user["email"])

    return AuthResponse(
        token=token,
        user_id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
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
    )
