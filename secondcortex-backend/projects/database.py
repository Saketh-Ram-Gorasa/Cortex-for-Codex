from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Any

from auth.database import _get_db_path


class ProjectDB:
    def __init__(self) -> None:
        self.db_path = _get_db_path()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    slug TEXT,
                    visibility TEXT NOT NULL DEFAULT 'private',
                    team_id TEXT,
                    workspace_name TEXT,
                    workspace_path_hash TEXT,
                    repo_remote TEXT,
                    is_archived INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_projects_owner_archived ON projects (owner_user_id, is_archived)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_projects_team_visibility_archived ON projects (team_id, visibility, is_archived)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_projects_workspace_hash ON projects (owner_user_id, workspace_path_hash)"
            )
            conn.commit()

    @staticmethod
    def _row_to_project(row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "id": row[0],
            "owner_user_id": row[1],
            "name": row[2],
            "slug": row[3],
            "visibility": row[4],
            "team_id": row[5],
            "workspace_name": row[6],
            "workspace_path_hash": row[7],
            "repo_remote": row[8],
            "is_archived": bool(row[9]),
            "created_at": int(row[10]),
            "updated_at": int(row[11]),
        }

    def create_project(
        self,
        owner_user_id: str,
        name: str,
        visibility: str = "private",
        team_id: str | None = None,
        slug: str | None = None,
        workspace_name: str | None = None,
        workspace_path_hash: str | None = None,
        repo_remote: str | None = None,
    ) -> dict[str, Any]:
        project_id = str(uuid.uuid4())
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    id, owner_user_id, name, slug, visibility, team_id,
                    workspace_name, workspace_path_hash, repo_remote,
                    is_archived, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    project_id,
                    owner_user_id,
                    name,
                    slug,
                    visibility,
                    team_id,
                    workspace_name,
                    workspace_path_hash,
                    repo_remote,
                    now,
                    now,
                ),
            )
            conn.commit()

        return self.get_project_by_id(project_id)

    def get_project_by_id(self, project_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT id, owner_user_id, name, slug, visibility, team_id,
                       workspace_name, workspace_path_hash, repo_remote,
                       is_archived, created_at, updated_at
                FROM projects
                WHERE id = ?
                """,
                (project_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_project(row)

    def list_visible_projects(
        self,
        user_id: str,
        team_id: str | None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        archived_value = 1 if include_archived else 0
        with sqlite3.connect(self.db_path) as conn:
            if team_id:
                rows = conn.execute(
                    """
                    SELECT id, owner_user_id, name, slug, visibility, team_id,
                           workspace_name, workspace_path_hash, repo_remote,
                           is_archived, created_at, updated_at
                    FROM projects
                    WHERE (owner_user_id = ? OR (visibility = 'team' AND team_id = ?))
                      AND is_archived = ?
                    ORDER BY updated_at DESC
                    """,
                    (user_id, team_id, archived_value),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, owner_user_id, name, slug, visibility, team_id,
                           workspace_name, workspace_path_hash, repo_remote,
                           is_archived, created_at, updated_at
                    FROM projects
                    WHERE owner_user_id = ?
                      AND is_archived = ?
                    ORDER BY updated_at DESC
                    """,
                    (user_id, archived_value),
                ).fetchall()

        return [self._row_to_project(row) for row in rows]

    def user_can_access_project(self, user_id: str, team_id: str | None, project_id: str) -> bool:
        project = self.get_project_by_id(project_id)
        if not project:
            return False
        if project["owner_user_id"] == user_id:
            return True
        if team_id and project["visibility"] == "team" and project.get("team_id") == team_id:
            return True
        return False

    def update_project(
        self,
        project_id: str,
        owner_user_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        allowed_fields = {
            "name",
            "slug",
            "visibility",
            "team_id",
            "workspace_name",
            "workspace_path_hash",
            "repo_remote",
        }
        fields = [field for field in updates.keys() if field in allowed_fields]
        if not fields:
            return self.get_project_by_id(project_id)

        now = int(time.time())
        assignments = ", ".join([f"{field} = ?" for field in fields] + ["updated_at = ?"])
        values = [updates[field] for field in fields] + [now, project_id, owner_user_id]

        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                f"""
                UPDATE projects
                SET {assignments}
                WHERE id = ? AND owner_user_id = ?
                """,
                values,
            )
            conn.commit()
            if result.rowcount == 0:
                return None

        return self.get_project_by_id(project_id)

    def set_archived_state(self, project_id: str, owner_user_id: str, is_archived: bool) -> dict[str, Any] | None:
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                """
                UPDATE projects
                SET is_archived = ?, updated_at = ?
                WHERE id = ? AND owner_user_id = ?
                """,
                (1 if is_archived else 0, now, project_id, owner_user_id),
            )
            conn.commit()
            if result.rowcount == 0:
                return None
        return self.get_project_by_id(project_id)

    def delete_project(self, project_id: str, owner_user_id: str) -> bool:
        """Hard-delete a project. Only the owner can delete."""
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "DELETE FROM projects WHERE id = ? AND owner_user_id = ?",
                (project_id, owner_user_id),
            )
            conn.commit()
            return int(result.rowcount or 0) > 0

    def resolve_candidates(
        self,
        user_id: str,
        team_id: str | None,
        workspace_name: str,
        workspace_path_hash: str,
        repo_remote: str,
    ) -> list[dict[str, Any]]:
        projects = self.list_visible_projects(user_id=user_id, team_id=team_id, include_archived=False)

        normalized_workspace_name = (workspace_name or "").strip().lower()
        normalized_workspace_hash = (workspace_path_hash or "").strip().lower()
        normalized_repo_remote = (repo_remote or "").strip().lower()

        candidates: list[dict[str, Any]] = []
        for project in projects:
            score = 0.0

            project_workspace_name = str(project.get("workspace_name") or "").strip().lower()
            project_workspace_hash = str(project.get("workspace_path_hash") or "").strip().lower()
            project_repo_remote = str(project.get("repo_remote") or "").strip().lower()

            if normalized_workspace_hash and project_workspace_hash and normalized_workspace_hash == project_workspace_hash:
                score += 0.6
            if normalized_repo_remote and project_repo_remote and normalized_repo_remote == project_repo_remote:
                score += 0.3
            if normalized_workspace_name and project_workspace_name and normalized_workspace_name == project_workspace_name:
                score += 0.2

            if score <= 0:
                continue

            candidates.append(
                {
                    "projectId": project["id"],
                    "name": project["name"],
                    "confidence": min(score, 1.0),
                }
            )

        candidates.sort(key=lambda candidate: candidate["confidence"], reverse=True)
        return candidates
