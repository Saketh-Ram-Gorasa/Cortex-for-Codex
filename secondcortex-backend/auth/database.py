"""
SQLite-backed user database for SecondCortex authentication.
Uses persistent storage on Azure (/home/auth.db).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import sqlite3
import uuid
from pathlib import Path

from config import settings

logger = logging.getLogger("secondcortex.auth.database")


def _get_db_path() -> str:
    """Use the same persistent storage root as ChromaDB."""
    base = settings.chroma_db_path  # /home/chroma_db on Azure, ./chroma_db locally
    db_dir = str(Path(base).parent)  # /home on Azure, . locally
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "auth.db")


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Hash password with PBKDF2-SHA256. Returns (hash_hex, salt_hex)."""
    if salt is None:
        salt = os.urandom(32).hex()
    pw_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        iterations=100_000,
    )
    return pw_hash.hex(), salt


def _verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verify a password against stored hash."""
    computed_hash, _ = _hash_password(password, salt)
    return hmac.compare_digest(computed_hash, stored_hash)


class UserDB:
    """Manages user accounts in SQLite."""

    def __init__(self) -> None:
        self.db_path = _get_db_path()
        self._init_db()
        logger.info("Auth database initialized at: %s", self.db_path)

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def create_user(self, email: str, password: str, display_name: str = "") -> dict | None:
        """Create a new user. Returns user dict or None if email already exists."""
        email = email.lower().strip()
        user_id = str(uuid.uuid4())[:8]  # Short user ID for collection namespacing
        pw_hash, salt = _hash_password(password)

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO users (id, email, password_hash, password_salt, display_name) VALUES (?, ?, ?, ?, ?)",
                    (user_id, email, pw_hash, salt, display_name or email.split("@")[0]),
                )
                conn.commit()
            logger.info("Created user: %s (%s)", user_id, email)
            return {"id": user_id, "email": email, "display_name": display_name or email.split("@")[0]}
        except sqlite3.IntegrityError:
            logger.warning("User already exists: %s", email)
            return None

    def authenticate(self, email: str, password: str) -> dict | None:
        """Verify credentials. Returns user dict or None."""
        email = email.lower().strip()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, email, password_hash, password_salt, display_name FROM users WHERE email = ?",
                (email,),
            ).fetchone()

        if row is None:
            return None

        user_id, user_email, stored_hash, salt, display_name = row
        if _verify_password(password, stored_hash, salt):
            return {"id": user_id, "email": user_email, "display_name": display_name}
        return None

    def get_user_by_id(self, user_id: str) -> dict | None:
        """Lookup a user by ID."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, email, display_name FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row:
            return {"id": row[0], "email": row[1], "display_name": row[2]}
        return None
