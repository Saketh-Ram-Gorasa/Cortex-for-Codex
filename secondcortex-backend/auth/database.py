"""
SQLite-backed user database for SecondCortex authentication.
Uses persistent storage on Azure (/home/auth.db).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
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


def _hash_api_secret(secret: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{secret}".encode("utf-8")).hexdigest()


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
                    project_id TEXT,
                    workspace TEXT NOT NULL,
                    active_file TEXT NOT NULL,
                    git_branch TEXT,
                    terminal_commands TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    enriched_context TEXT NOT NULL DEFAULT '{}',
                    timestamp INTEGER NOT NULL,
                    synced INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            try:
                conn.execute("ALTER TABLE synced_snapshots ADD COLUMN enriched_context TEXT NOT NULL DEFAULT '{}'")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE synced_snapshots ADD COLUMN project_id TEXT")
            except sqlite3.OperationalError:
                pass
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_synced_snapshots_scope
                ON synced_snapshots (team_id, user_id, timestamp DESC)
            """)
            # Create teams table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS teams (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    team_lead_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (team_lead_id) REFERENCES users (id)
                )
            """)
            # Create invite_codes table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS invite_codes (
                    code TEXT PRIMARY KEY,
                    team_id TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    used_by TEXT,
                    used_at TIMESTAMP,
                    FOREIGN KEY (team_id) REFERENCES teams (id),
                    FOREIGN KEY (created_by) REFERENCES users (id),
                    FOREIGN KEY (used_by) REFERENCES users (id)
                )
            """)
            # Create team_members table for explicit membership tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS team_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(team_id, user_id),
                    FOREIGN KEY (team_id) REFERENCES teams (id),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mcp_api_keys (
                    key_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    key_salt TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT 'default',
                    scopes TEXT NOT NULL DEFAULT 'memory:read',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    last_used_at TIMESTAMP,
                    is_revoked INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_mcp_api_keys_user_active
                ON mcp_api_keys (user_id, is_revoked, expires_at)
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

    def get_user_by_email(self, email: str) -> dict | None:
        """Lookup a user by email."""
        normalized_email = email.lower().strip()
        if not normalized_email:
            return None
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, email, display_name, team_id FROM users WHERE email = ?",
                (normalized_email,),
            ).fetchone()
        if row:
            return {"id": row[0], "email": row[1], "display_name": row[2], "team_id": row[3]}
        return None

    def get_most_active_user(self) -> dict | None:
        """Return the user with the largest snapshot history (fallback for guest login)."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT u.id, u.email, u.display_name, u.team_id
                FROM users u
                INNER JOIN (
                    SELECT user_id, COUNT(*) AS snapshot_count, MAX(timestamp) AS last_snapshot
                    FROM synced_snapshots
                    GROUP BY user_id
                    ORDER BY snapshot_count DESC, last_snapshot DESC
                    LIMIT 1
                ) s ON s.user_id = u.id
                """
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
                    id, user_id, team_id, project_id, workspace, active_file, git_branch,
                    terminal_commands, summary, enriched_context, timestamp, synced
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_id=excluded.user_id,
                    team_id=excluded.team_id,
                    project_id=excluded.project_id,
                    workspace=excluded.workspace,
                    active_file=excluded.active_file,
                    git_branch=excluded.git_branch,
                    terminal_commands=excluded.terminal_commands,
                    summary=excluded.summary,
                    enriched_context=excluded.enriched_context,
                    timestamp=excluded.timestamp,
                    synced=excluded.synced
                """,
                (
                    row.get("id"),
                    row.get("user_id"),
                    row.get("team_id"),
                    row.get("project_id"),
                    row.get("workspace"),
                    row.get("active_file"),
                    row.get("git_branch"),
                    row.get("terminal_commands") or "[]",
                    row.get("summary") or "",
                    row.get("enriched_context") or "{}",
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
                    SELECT id, user_id, team_id, project_id, workspace, active_file, git_branch,
                              terminal_commands, summary, enriched_context, timestamp, synced
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
                        "project_id": row[3],
                        "workspace": row[4],
                        "active_file": row[5],
                        "git_branch": row[6],
                        "terminal_commands": row[7],
                        "summary": row[8],
                        "enriched_context": row[9],
                        "timestamp": row[10],
                        "synced": row[11],
                    })

        all_rows.sort(key=lambda r: int(r.get("timestamp") or 0), reverse=True)
        return all_rows

    def get_user_snapshots(self, user_id: str, limit: int = 1000) -> list[dict]:
        """Return one user's synced snapshots, newest first."""
        capped_limit = max(1, min(limit, 5000))
        rows: list[dict] = []

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, user_id, team_id, project_id, workspace, active_file, git_branch,
                          terminal_commands, summary, enriched_context, timestamp, synced
                FROM synced_snapshots
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (user_id, capped_limit),
            )
            for row in cursor.fetchall():
                rows.append({
                    "id": row[0],
                    "user_id": row[1],
                    "team_id": row[2],
                    "project_id": row[3],
                    "workspace": row[4],
                    "active_file": row[5],
                    "git_branch": row[6],
                    "terminal_commands": row[7],
                    "summary": row[8],
                    "enriched_context": row[9],
                    "timestamp": row[10],
                    "synced": row[11],
                })

        return rows

    def get_sync_checkpoint(self, user_id: str) -> int:
        """Checkpoint = max timestamp visible to user in team scope."""
        snapshots = self.get_team_snapshots(user_id=user_id, per_member_limit=500)
        if not snapshots:
            return 0
        return max(int(s.get("timestamp") or 0) for s in snapshots)

    def generate_mcp_api_key(self, user_id: str) -> str:
        """Generate a new MCP API key for the user and save it.

        Compatibility helper used by existing routes.
        """
        issued = self.issue_mcp_api_key(user_id=user_id)
        return issued["api_key"]

    def issue_mcp_api_key(
        self,
        user_id: str,
        *,
        name: str = "default",
        scopes: list[str] | None = None,
        ttl_days: int | None = None,
    ) -> dict:
        """Issue a scoped, expiring MCP API key and return the plaintext value once."""
        scopes = scopes or ["memory:read"]
        key_id = uuid.uuid4().hex[:12]
        key_secret = secrets.token_urlsafe(32)
        api_key = f"sc_mcp_{key_id}_{key_secret}"
        key_salt = secrets.token_hex(16)
        key_hash = _hash_api_secret(key_secret, key_salt)
        ttl = max(1, ttl_days or int(settings.mcp_key_ttl_days))
        expires_at = datetime.now(timezone.utc) + timedelta(days=ttl)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO mcp_api_keys (key_id, user_id, key_hash, key_salt, name, scopes, expires_at, is_revoked)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    key_id,
                    user_id,
                    key_hash,
                    key_salt,
                    name.strip() or "default",
                    ",".join(sorted({s.strip() for s in scopes if s and s.strip()})) or "memory:read",
                    expires_at.isoformat(),
                ),
            )
            conn.execute(
                "UPDATE users SET mcp_api_key = ? WHERE id = ?",
                (api_key, user_id),
            )
            conn.commit()
        logger.info("Issued MCP API key for user=%s key_id=%s", user_id, key_id)
        return {
            "api_key": api_key,
            "key_id": key_id,
            "name": name.strip() or "default",
            "scopes": scopes,
            "expires_at": expires_at.isoformat(),
        }

    def list_mcp_api_keys(self, user_id: str) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT key_id, name, scopes, created_at, expires_at, last_used_at, is_revoked
                FROM mcp_api_keys
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            ).fetchall()

        return [
            {
                "key_id": row[0],
                "name": row[1],
                "scopes": [s for s in str(row[2] or "").split(",") if s],
                "created_at": row[3],
                "expires_at": row[4],
                "last_used_at": row[5],
                "is_revoked": bool(row[6]),
            }
            for row in rows
        ]

    def revoke_mcp_api_key(self, user_id: str, key_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE mcp_api_keys SET is_revoked = 1 WHERE user_id = ? AND key_id = ?",
                (user_id, key_id),
            )
            conn.execute(
                """
                UPDATE users
                SET mcp_api_key = NULL
                WHERE id = ? AND mcp_api_key LIKE ?
                """,
                (user_id, f"sc_mcp_{key_id}_%"),
            )
            conn.commit()
            return int(cursor.rowcount or 0) > 0

    def _lookup_new_style_mcp_key(self, api_key: str) -> dict | None:
        if not api_key or not api_key.startswith("sc_mcp_"):
            return None

        parts = api_key.split("_", 3)
        if len(parts) != 4:
            return None

        key_id = parts[2].strip()
        key_secret = parts[3].strip()
        if not key_id or not key_secret:
            return None

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT k.user_id, u.email, u.display_name, k.scopes, k.expires_at, k.key_hash, k.key_salt, k.is_revoked
                FROM mcp_api_keys k
                JOIN users u ON u.id = k.user_id
                WHERE k.key_id = ?
                """,
                (key_id,),
            ).fetchone()

            if not row:
                return None

            user_id, email, display_name, scopes_raw, expires_at_raw, key_hash, key_salt, is_revoked = row
            if int(is_revoked or 0) == 1:
                return None

            expected_hash = _hash_api_secret(key_secret, str(key_salt))
            if not hmac.compare_digest(str(key_hash), expected_hash):
                return None

            if expires_at_raw:
                try:
                    expires_at = datetime.fromisoformat(str(expires_at_raw).replace("Z", "+00:00"))
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    if expires_at < datetime.now(timezone.utc):
                        return None
                except ValueError:
                    return None

            conn.execute(
                "UPDATE mcp_api_keys SET last_used_at = ? WHERE key_id = ?",
                (datetime.now(timezone.utc).isoformat(), key_id),
            )
            conn.commit()

        return {
            "id": user_id,
            "email": email,
            "display_name": display_name,
            "scopes": [s for s in str(scopes_raw or "").split(",") if s],
        }

    def get_user_by_mcp_api_key(self, api_key: str) -> dict | None:
        """Lookup a user by their MCP API key."""
        new_style_user = self._lookup_new_style_mcp_key(api_key)
        if new_style_user is not None:
            return new_style_user

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

    def create_team(self, team_id: str, name: str, team_lead_id: str) -> dict:
        """Create a new team. Verify team_lead_id exists as a user first."""
        with sqlite3.connect(self.db_path) as conn:
            # Verify team lead exists
            cursor = conn.execute("SELECT id FROM users WHERE id = ?", (team_lead_id,))
            if not cursor.fetchone():
                raise ValueError(f"User {team_lead_id} does not exist")
            
            # Create the team
            conn.execute(
                "INSERT INTO teams (id, name, team_lead_id) VALUES (?, ?, ?)",
                (team_id, name, team_lead_id),
            )
            
            # Update team lead's team_id
            conn.execute("UPDATE users SET team_id = ? WHERE id = ?", (team_id, team_lead_id))
            
            # Add team lead to team_members
            conn.execute(
                "INSERT INTO team_members (team_id, user_id) VALUES (?, ?)",
                (team_id, team_lead_id),
            )
            
            conn.commit()
        return {"id": team_id, "name": name, "team_lead_id": team_lead_id}

    def generate_invite_code(self, team_id: str, created_by: str) -> str:
        """Generate a random 8-character invite code for a team."""
        import secrets
        import string
        
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        
        with sqlite3.connect(self.db_path) as conn:
            # Verify team exists
            cursor = conn.execute("SELECT id FROM teams WHERE id = ?", (team_id,))
            if not cursor.fetchone():
                raise ValueError(f"Team {team_id} does not exist")
            
            conn.execute(
                "INSERT INTO invite_codes (code, team_id, created_by) VALUES (?, ?, ?)",
                (code, team_id, created_by),
            )
            conn.commit()
        
        return code

    def join_team_with_code(self, user_id: str, code: str) -> bool:
        """Join a team using an invite code. Returns True if successful."""
        with sqlite3.connect(self.db_path) as conn:
            # Check if code exists and is unused
            cursor = conn.execute(
                "SELECT team_id FROM invite_codes WHERE code = ? AND used_by IS NULL",
                (code,),
            )
            row = cursor.fetchone()
            if not row:
                return False
            
            team_id = row[0]
            
            # Update user's team_id
            conn.execute("UPDATE users SET team_id = ? WHERE id = ?", (team_id, user_id))
            
            # Mark code as used
            conn.execute(
                "UPDATE invite_codes SET used_by = ?, used_at = CURRENT_TIMESTAMP WHERE code = ?",
                (user_id, code),
            )
            
            # Add to team_members table
            conn.execute(
                "INSERT INTO team_members (team_id, user_id) VALUES (?, ?)",
                (team_id, user_id),
            )
            
            conn.commit()
        return True

    def get_team_members(self, team_id: str) -> list[dict]:
        """Get all members of a team."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT u.id, u.email, u.display_name, u.created_at 
                FROM users u
                INNER JOIN team_members tm ON u.id = tm.user_id
                WHERE tm.team_id = ?
                ORDER BY tm.joined_at ASC
                """,
                (team_id,),
            )
            rows = cursor.fetchall()
            if rows:
                return [
                    {"id": r[0], "email": r[1], "display_name": r[2], "created_at": r[3]}
                    for r in rows
                ]

            # Fallback 1: users table team_id assignment.
            fallback_users = conn.execute(
                """
                SELECT id, email, display_name, created_at
                FROM users
                WHERE team_id = ?
                ORDER BY created_at ASC
                """,
                (team_id,),
            ).fetchall()
            if fallback_users:
                return [
                    {"id": r[0], "email": r[1], "display_name": r[2], "created_at": r[3]}
                    for r in fallback_users
                ]

            # Fallback 2: infer members from snapshot history in this team scope.
            snapshot_users = conn.execute(
                """
                SELECT u.id, u.email, u.display_name, u.created_at
                FROM users u
                INNER JOIN (
                    SELECT DISTINCT user_id
                    FROM synced_snapshots
                    WHERE team_id = ?
                ) ss ON ss.user_id = u.id
                ORDER BY u.created_at ASC
                """,
                (team_id,),
            ).fetchall()
            return [
                {"id": r[0], "email": r[1], "display_name": r[2], "created_at": r[3]}
                for r in snapshot_users
            ]

    def get_team_info(self, team_id: str) -> dict | None:
        """Get team info including lead and member count."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, name, team_lead_id, created_at FROM teams WHERE id = ?
                """,
                (team_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            
            # Get member count
            count_cursor = conn.execute(
                "SELECT COUNT(*) FROM team_members WHERE team_id = ?", (team_id,)
            )
            member_count = count_cursor.fetchone()[0]
            
            return {
                "id": row[0],
                "name": row[1],
                "team_lead_id": row[2],
                "created_at": row[3],
                "member_count": member_count,
            }

    def get_most_active_team_id(self) -> str | None:
        """Return the team_id with the most recent/highest snapshot activity."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT team_id
                FROM synced_snapshots
                WHERE team_id IS NOT NULL AND TRIM(team_id) != ''
                GROUP BY team_id
                ORDER BY COUNT(*) DESC, MAX(timestamp) DESC
                LIMIT 1
                """
            ).fetchone()
            if row and row[0]:
                return str(row[0])

            # Fallback if snapshot rows are sparse/missing team_id values.
            row = conn.execute(
                """
                SELECT team_id
                FROM users
                WHERE team_id IS NOT NULL AND TRIM(team_id) != ''
                GROUP BY team_id
                ORDER BY COUNT(*) DESC
                LIMIT 1
                """
            ).fetchone()
            if row and row[0]:
                return str(row[0])

        return None

    def get_user_teams(self, user_id: str) -> list[dict]:
        """Return all teams a user belongs to (supports historical memberships)."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT t.id, t.name, t.team_lead_id, t.created_at, COUNT(tm2.user_id) as member_count
                FROM teams t
                INNER JOIN team_members tm ON tm.team_id = t.id
                LEFT JOIN team_members tm2 ON tm2.team_id = t.id
                WHERE tm.user_id = ?
                GROUP BY t.id, t.name, t.team_lead_id, t.created_at
                ORDER BY t.created_at DESC
                """,
                (user_id,),
            ).fetchall()

            if rows:
                return [
                    {
                        "id": r[0],
                        "name": r[1],
                        "team_lead_id": r[2],
                        "created_at": r[3],
                        "member_count": int(r[4] or 0),
                    }
                    for r in rows
                ]

            user_row = conn.execute(
                "SELECT team_id FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not user_row or not user_row[0]:
                return []

            fallback_team = self.get_team_info(str(user_row[0]))
            return [fallback_team] if fallback_team else []

    def is_user_in_team(self, user_id: str, team_id: str) -> bool:
        """Check membership by team_members first, then users.team_id fallback."""
        with sqlite3.connect(self.db_path) as conn:
            membership = conn.execute(
                "SELECT 1 FROM team_members WHERE team_id = ? AND user_id = ? LIMIT 1",
                (team_id, user_id),
            ).fetchone()
            if membership:
                return True

            fallback = conn.execute(
                "SELECT 1 FROM users WHERE id = ? AND team_id = ? LIMIT 1",
                (user_id, team_id),
            ).fetchone()
            return bool(fallback)
