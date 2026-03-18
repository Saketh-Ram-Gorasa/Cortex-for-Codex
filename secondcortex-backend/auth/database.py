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
                    team_id TEXT,
                    display_name TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    mcp_api_key TEXT UNIQUE
                )
            """)
            # Migration to add mcp_api_key to existing users table
            try:
                conn.execute("ALTER TABLE users ADD COLUMN mcp_api_key TEXT")
            except sqlite3.OperationalError:
                # Column already exists
                pass
            try:
                conn.execute("ALTER TABLE users ADD COLUMN team_id TEXT")
            except sqlite3.OperationalError:
                pass
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    session_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (session_id) REFERENCES chat_sessions (id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS synced_snapshots (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    team_id TEXT,
                    workspace TEXT NOT NULL,
                    active_file TEXT NOT NULL,
                    git_branch TEXT,
                    terminal_commands TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    synced INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_synced_snapshots_scope
                ON synced_snapshots (team_id, user_id, timestamp DESC)
            """)
            conn.commit()

    def create_chat_session(self, user_id: str, title: str = "New Chat") -> str:
        """Create a new chat session and return its ID."""
        session_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO chat_sessions (id, user_id, title) VALUES (?, ?, ?)",
                (session_id, user_id, title),
            )
            conn.commit()
        return session_id

    def get_chat_sessions(self, user_id: str) -> list[dict]:
        """List all chat sessions for a user."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id, title, created_at FROM chat_sessions WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
            rows = cursor.fetchall()
            return [{"id": r[0], "title": r[1], "created_at": r[2]} for r in rows]

    def save_chat_message(self, user_id: str, role: str, content: str, session_id: str | None = None) -> None:
        """Save a chat message to a specific session."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO chat_messages (user_id, session_id, role, content) VALUES (?, ?, ?, ?)",
                (user_id, session_id, role, content),
            )
            conn.commit()

    def get_chat_history(self, user_id: str, session_id: str | None = None, limit: int = 50) -> list[dict]:
        """Retrieve chat history, optionally filtered by session."""
        query = "SELECT role, content, timestamp FROM chat_messages WHERE user_id = ?"
        params = [user_id]
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        else:
            query += " AND session_id IS NULL"
        
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(rows)]

    def delete_chat_history(self, user_id: str, session_id: str | None = None) -> None:
        """Clear chat history (single session or all if none specified)."""
        with sqlite3.connect(self.db_path) as conn:
            if session_id:
                conn.execute("DELETE FROM chat_messages WHERE user_id = ? AND session_id = ?", (user_id, session_id))
                conn.execute("DELETE FROM chat_sessions WHERE user_id = ? AND id = ?", (user_id, session_id))
            else:
                conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM chat_sessions WHERE user_id = ?", (user_id,))
            conn.commit()


    def create_user(self, email: str, password: str, display_name: str = "", team_id: str | None = None) -> dict | None:
        """Create a new user. Returns user dict or None if email already exists."""
        email = email.lower().strip()
        user_id = str(uuid.uuid4())[:8]  # Short user ID for collection namespacing
        pw_hash, salt = _hash_password(password)

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO users (id, email, password_hash, password_salt, display_name, team_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, email, pw_hash, salt, display_name or email.split("@")[0], team_id),
                )
                conn.commit()
            logger.info("Created user: %s (%s)", user_id, email)
            return {
                "id": user_id,
                "email": email,
                "display_name": display_name or email.split("@")[0],
                "team_id": team_id,
            }
        except sqlite3.IntegrityError:
            logger.warning("User already exists: %s", email)
            return None

    def authenticate(self, email: str, password: str) -> dict | None:
        """Verify credentials. Returns user dict or None."""
        email = email.lower().strip()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, email, password_hash, password_salt, display_name, team_id FROM users WHERE email = ?",
                (email,),
            ).fetchone()

        if row is None:
            return None

        user_id, user_email, stored_hash, salt, display_name, team_id = row
        if _verify_password(password, stored_hash, salt):
            return {"id": user_id, "email": user_email, "display_name": display_name, "team_id": team_id}
        return None

    def get_user_by_id(self, user_id: str) -> dict | None:
        """Lookup a user by ID."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, email, display_name, team_id FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row:
            return {"id": row[0], "email": row[1], "display_name": row[2], "team_id": row[3]}
        return None

    def get_team_member_ids(self, user_id: str) -> list[str]:
        """Return all user IDs visible to this user by team scope rules."""
        user = self.get_user_by_id(user_id)
        if not user:
            return []

        team_id = user.get("team_id")
        with sqlite3.connect(self.db_path) as conn:
            if team_id:
                rows = conn.execute(
                    "SELECT id FROM users WHERE team_id = ? ORDER BY created_at DESC",
                    (team_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id FROM users WHERE id = ?",
                    (user_id,),
                ).fetchall()
        return [str(r[0]) for r in rows]

    def upsert_synced_snapshot(self, row: dict) -> None:
        """Store one synced snapshot row in raw storage table."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO synced_snapshots (
                    id, user_id, team_id, workspace, active_file, git_branch,
                    terminal_commands, summary, timestamp, synced
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_id=excluded.user_id,
                    team_id=excluded.team_id,
                    workspace=excluded.workspace,
                    active_file=excluded.active_file,
                    git_branch=excluded.git_branch,
                    terminal_commands=excluded.terminal_commands,
                    summary=excluded.summary,
                    timestamp=excluded.timestamp,
                    synced=excluded.synced
                """,
                (
                    row.get("id"),
                    row.get("user_id"),
                    row.get("team_id"),
                    row.get("workspace"),
                    row.get("active_file"),
                    row.get("git_branch"),
                    row.get("terminal_commands") or "[]",
                    row.get("summary") or "",
                    int(row.get("timestamp") or 0),
                    int(row.get("synced") or 0),
                ),
            )
            conn.commit()

    def get_team_snapshots(self, user_id: str, per_member_limit: int = 500) -> list[dict]:
        """Return team-scoped snapshots, capped per member, newest first."""
        member_ids = self.get_team_member_ids(user_id)
        if not member_ids:
            return []

        all_rows: list[dict] = []
        with sqlite3.connect(self.db_path) as conn:
            for member_id in member_ids:
                cursor = conn.execute(
                    """
                    SELECT id, user_id, team_id, workspace, active_file, git_branch,
                           terminal_commands, summary, timestamp, synced
                    FROM synced_snapshots
                    WHERE user_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (member_id, per_member_limit),
                )
                for row in cursor.fetchall():
                    all_rows.append({
                        "id": row[0],
                        "user_id": row[1],
                        "team_id": row[2],
                        "workspace": row[3],
                        "active_file": row[4],
                        "git_branch": row[5],
                        "terminal_commands": row[6],
                        "summary": row[7],
                        "timestamp": row[8],
                        "synced": row[9],
                    })

        all_rows.sort(key=lambda r: int(r.get("timestamp") or 0), reverse=True)
        return all_rows

    def get_sync_checkpoint(self, user_id: str) -> int:
        """Checkpoint = max timestamp visible to user in team scope."""
        snapshots = self.get_team_snapshots(user_id=user_id, per_member_limit=500)
        if not snapshots:
            return 0
        return max(int(s.get("timestamp") or 0) for s in snapshots)

    def generate_mcp_api_key(self, user_id: str) -> str:
        """Generate a new MCP API key for the user and save it."""
        import secrets
        new_key = f"sc_mcp_{secrets.token_urlsafe(32)}"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET mcp_api_key = ? WHERE id = ?",
                (new_key, user_id),
            )
            conn.commit()
        logger.info("Generated new MCP API key for user: %s", user_id)
        return new_key

    def get_user_by_mcp_api_key(self, api_key: str) -> dict | None:
        """Lookup a user by their MCP API key."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, email, display_name FROM users WHERE mcp_api_key = ?",
                (api_key,),
            ).fetchone()
        if row:
            return {"id": row[0], "email": row[1], "display_name": row[2]}
        return None

    def get_mcp_api_key(self, user_id: str) -> str | None:
        """Get the current MCP API key for a user."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT mcp_api_key FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row:
            return row[0]
        return None
