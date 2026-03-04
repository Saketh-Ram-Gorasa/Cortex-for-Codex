"""
JWT token creation and verification for SecondCortex.
"""

from __future__ import annotations

import logging
import time

import jwt

from config import settings

logger = logging.getLogger("secondcortex.auth.jwt")

ALGORITHM = "HS256"
TOKEN_EXPIRY_SECONDS = 7 * 24 * 3600  # 7 days


def _get_secret() -> str:
    """Get JWT secret from settings."""
    secret = settings.jwt_secret
    if not secret:
        raise RuntimeError("JWT_SECRET is not set. Add it to your .env file.")
    return secret


def create_token(user_id: str, email: str) -> str:
    """Create a signed JWT token."""
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, _get_secret(), algorithm=ALGORITHM)


def verify_token(token: str) -> dict | None:
    """Verify and decode a JWT token. Returns payload or None."""
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired.")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid token: %s", e)
        return None
