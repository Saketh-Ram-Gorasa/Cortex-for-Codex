"""
Plug-and-play summary generation service for teams.
Generates daily/weekly summaries that can be consumed by multiple dashboards.
"""

from __future__ import annotations

import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import settings
from models.schemas import TeamDailySummary, TeamWeeklySummary, MemberSummary
from auth.database import UserDB
from services.vector_db import VectorDBService

logger = logging.getLogger("secondcortex.services.summary_service")


class SummaryService:
    """Generate reusable team and individual summaries."""

    def __init__(self):
        self.db_path = str(Path(settings.chroma_db_path).parent / "auth.db")
        self.user_db = UserDB()
        self.vector_db = VectorDBService()

    def generate_daily_summary(self, team_id: str) -> dict:
        """
        Generate a daily summary for a team.
        Returns dict compatible with TeamDailySummary schema.
        """
        members = self.user_db.get_team_members(team_id)
        
        member_summaries = []
        total_snapshots = 0
        total_commits = 0
        active_members = 0
        
        member_rows = self._compute_members_activity(members, days=1)
        for row in member_rows:
            if row["is_active"]:
                active_members += 1
            total_snapshots += row["snapshot_count"]
            total_commits += row["commit_count"]
            member_summaries.append(row["summary"])
        
        return {
            "team_id": team_id,
            "period": "daily",
            "members": [m.model_dump() for m in member_summaries],
            "total_snapshots": total_snapshots,
            "total_commits": total_commits,
            "active_members": active_members,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def generate_weekly_summary(self, team_id: str) -> dict:
        """
        Generate a weekly summary for a team.
        Returns dict compatible with TeamWeeklySummary schema.
        """
        members = self.user_db.get_team_members(team_id)
        
        member_summaries = []
        total_snapshots = 0
        total_commits = 0
        active_members = 0
        daily_breakdown = {}
        
        member_rows = self._compute_members_activity(members, days=7)
        date_counts: dict[datetime.date, int] = {}
        for row in member_rows:
            if row["is_active"]:
                active_members += 1

            total_snapshots += row["snapshot_count"]
            total_commits += row["commit_count"]
            member_summaries.append(row["summary"])

            for entry in row["activity"]:
                day_dt = entry["timestamp"].date()
                date_counts[day_dt] = date_counts.get(day_dt, 0) + 1

        # Build daily breakdown for the week from already-fetched activity
        now = datetime.utcnow()
        for i in range(7):
            day_dt = (now - timedelta(days=i)).date()
            day = (now - timedelta(days=i)).strftime("%A")
            daily_breakdown[day] = date_counts.get(day_dt, 0)
        
        return {
            "team_id": team_id,
            "period": "weekly",
            "members": [m.model_dump() for m in member_summaries],
            "total_snapshots": total_snapshots,
            "total_commits": total_commits,
            "active_members": active_members,
            "daily_breakdown": daily_breakdown,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _compute_members_activity(self, members: list[dict], days: int) -> list[dict]:
        if not members:
            return []

        max_workers = max(1, min(8, len(members)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(lambda member: self._compute_member_activity(member, days), members))

    def _compute_member_activity(self, member: dict, days: int) -> dict:
        user_id = member["id"]
        activity = self._get_user_vector_activity_window(user_id, days=days)
        snapshot_count = len(activity)
        commit_count = self._get_commit_count(user_id, days=days)

        languages = self._infer_languages_from_files([entry["active_file"] for entry in activity])
        files_modified = len({entry["active_file"] for entry in activity if entry["active_file"]})
        is_active = snapshot_count > 0 or commit_count > 0

        summary = MemberSummary(
            user_id=user_id,
            display_name=member["display_name"],
            email=member["email"],
            snapshots_count=snapshot_count,
            commits_count=commit_count,
            languages_used=languages,
            files_modified=files_modified,
            status="active" if is_active else "idle",
        )
        return {
            "summary": summary,
            "snapshot_count": snapshot_count,
            "commit_count": commit_count,
            "is_active": is_active,
            "activity": activity,
        }

    def generate_user_daily_summary(self, user_id: str) -> dict:
        """
        Generate a daily summary for an individual user.
        Returns dict compatible with summary response format with single-member array.
        """
        user = self.user_db.get_user_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        user_activity = self._get_user_vector_activity(user_id)
        now = datetime.utcnow()
        daily_cutoff = now - timedelta(hours=24)
        daily_activity = [entry for entry in user_activity if entry["timestamp"] >= daily_cutoff]

        snapshot_count = len(daily_activity)
        
        # Get commits for today
        commit_count = self._get_commit_count(user_id, days=1)
        
        # Get languages/files used from timeline
        languages = self._infer_languages_from_files([entry["active_file"] for entry in daily_activity])
        files_modified = len({entry["active_file"] for entry in daily_activity if entry["active_file"]})
        
        is_active = snapshot_count > 0 or commit_count > 0
        
        member_summary = MemberSummary(
            user_id=user_id,
            display_name=user.get("display_name", user_id),
            email=user.get("email", ""),
            snapshots_count=snapshot_count,
            commits_count=commit_count,
            languages_used=languages,
            files_modified=files_modified,
            status="active" if is_active else "idle",
        )
        
        return {
            "user_id": user_id,
            "period": "daily",
            "members": [member_summary.model_dump()],
            "total_snapshots": snapshot_count,
            "total_commits": commit_count,
            "active_members": 1 if is_active else 0,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def generate_user_weekly_summary(self, user_id: str) -> dict:
        """
        Generate a weekly summary for an individual user.
        Returns dict compatible with summary response format with single-member array.
        """
        user = self.user_db.get_user_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        user_activity = self._get_user_vector_activity(user_id)
        now = datetime.utcnow()
        weekly_cutoff = now - timedelta(days=7)
        weekly_activity = [entry for entry in user_activity if entry["timestamp"] >= weekly_cutoff]

        # Get snapshot count for this week
        snapshot_count = len(weekly_activity)
        
        # Get commits for this week
        commit_count = self._get_commit_count(user_id, days=7)
        
        # Get languages/files used from timeline
        languages = self._infer_languages_from_files([entry["active_file"] for entry in weekly_activity])
        files_modified = len({entry["active_file"] for entry in weekly_activity if entry["active_file"]})
        
        is_active = snapshot_count > 0 or commit_count > 0
        
        member_summary = MemberSummary(
            user_id=user_id,
            display_name=user.get("display_name", user_id),
            email=user.get("email", ""),
            snapshots_count=snapshot_count,
            commits_count=commit_count,
            languages_used=languages,
            files_modified=files_modified,
            status="active" if is_active else "idle",
        )
        
        # Build daily breakdown for the week
        daily_breakdown = {}
        for i in range(7):
            day_dt = (now - timedelta(days=i)).date()
            day = (now - timedelta(days=i)).strftime("%A")
            count = sum(1 for entry in weekly_activity if entry["timestamp"].date() == day_dt)
            daily_breakdown[day] = count
        
        return {
            "user_id": user_id,
            "period": "weekly",
            "members": [member_summary.model_dump()],
            "total_snapshots": snapshot_count,
            "total_commits": commit_count,
            "active_members": 1 if is_active else 0,
            "daily_breakdown": daily_breakdown,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _parse_snapshot_timestamp(self, value: object) -> datetime | None:
        if isinstance(value, (int, float)):
            numeric = float(value)
            if numeric > 1_000_000_000_000:
                numeric = numeric / 1000.0
            try:
                return datetime.utcfromtimestamp(numeric)
            except (OverflowError, OSError, ValueError):
                return None

        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None

            try:
                numeric = float(raw)
                if numeric > 1_000_000_000_000:
                    numeric = numeric / 1000.0
                return datetime.utcfromtimestamp(numeric)
            except ValueError:
                pass

            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                return parsed
            except ValueError:
                return None

        return None

    def _get_user_vector_activity(self, user_id: str) -> list[dict]:
        collection = self.vector_db._get_collection(user_id)
        if collection is None:
            return []

        try:
            total = collection.count() or 0
            if total <= 0:
                return []

            fetch_limit = min(total, 2500)
            result = collection.get(limit=fetch_limit, include=["metadatas"])
            metadatas = (result or {}).get("metadatas") or []

            activity: list[dict] = []
            for meta in metadatas:
                if not meta:
                    continue
                timestamp = self._parse_snapshot_timestamp(meta.get("timestamp"))
                if not timestamp:
                    continue
                activity.append(
                    {
                        "timestamp": timestamp,
                        "active_file": str(meta.get("active_file") or ""),
                    }
                )

            activity.sort(key=lambda row: row["timestamp"], reverse=True)
            return activity
        except Exception as exc:
            logger.error("Failed to compute vector activity for user=%s: %s", user_id, exc)
            return []

    def _get_user_vector_activity_window(self, user_id: str, days: int) -> list[dict]:
        activity = self._get_user_vector_activity(user_id)
        cutoff = datetime.utcnow() - timedelta(days=max(1, days))
        return [entry for entry in activity if entry["timestamp"] >= cutoff]

    def _get_team_vector_snapshot_count_for_day(self, team_id: str, days_ago: int) -> int:
        members = self.user_db.get_team_members(team_id)
        target_date = (datetime.utcnow() - timedelta(days=days_ago)).date()
        total = 0
        for member in members:
            user_id = member.get("id")
            if not user_id:
                continue
            activity = self._get_user_vector_activity(user_id)
            total += sum(1 for entry in activity if entry["timestamp"].date() == target_date)
        return total

    def _infer_languages_from_files(self, file_paths: list[str]) -> list[str]:
        extension_map = {
            "py": "Python",
            "ts": "TypeScript",
            "tsx": "TypeScript",
            "js": "JavaScript",
            "jsx": "JavaScript",
            "json": "JSON",
            "md": "Markdown",
            "css": "CSS",
            "html": "HTML",
            "yml": "YAML",
            "yaml": "YAML",
            "sql": "SQL",
            "sh": "Shell",
            "ps1": "PowerShell",
        }

        languages: set[str] = set()
        for file_path in file_paths:
            if not file_path or "." not in file_path:
                continue
            ext = file_path.rsplit(".", 1)[-1].lower()
            language = extension_map.get(ext)
            if language:
                languages.add(language)

        return sorted(languages)


    def _get_snapshot_count(self, user_id: str, team_id: str, days: int = 1) -> int:
        """Get snapshot count for a user in a team over N days."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        cutoff_ts = int(cutoff.timestamp())
        cutoff_ms = cutoff_ts * 1000
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM synced_snapshots
                WHERE user_id = ? AND team_id = ?
                  AND (
                    (timestamp < 1000000000000 AND timestamp >= ?)
                    OR (timestamp >= 1000000000000 AND timestamp >= ?)
                  )
                """,
                (user_id, team_id, cutoff_ts, cutoff_ms),
            )
            return cursor.fetchone()[0]

    def _get_user_snapshot_count(self, user_id: str, days: int = 1) -> int:
        """Get snapshot count for an individual user over N days (any team)."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        cutoff_ts = int(cutoff.timestamp())
        cutoff_ms = cutoff_ts * 1000
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM synced_snapshots
                WHERE user_id = ?
                  AND (
                    (timestamp < 1000000000000 AND timestamp >= ?)
                    OR (timestamp >= 1000000000000 AND timestamp >= ?)
                  )
                """,
                (user_id, cutoff_ts, cutoff_ms),
            )
            return cursor.fetchone()[0]

    def _get_commit_count(self, user_id: str, days: int = 1) -> int:
        """Placeholder: Get commit count from git history."""
        # This would integrate with your git ingest service
        # For now, return 0 as placeholder
        return 0

    def _get_languages_used(self, user_id: str, days: int = 1) -> list[str]:
        """Get unique languages used by a user in N days."""
        # TODO: Extract from active_file extensions or metadata
        # For now, return empty list as language data isn't stored in snapshots
        return []

    def _get_files_modified(self, user_id: str, days: int = 1) -> int:
        """Get count of unique files modified by user in N days."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        cutoff_ts = int(cutoff.timestamp())
        cutoff_ms = cutoff_ts * 1000
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT COUNT(DISTINCT active_file) FROM synced_snapshots
                WHERE user_id = ?
                  AND (
                    (timestamp < 1000000000000 AND timestamp >= ?)
                    OR (timestamp >= 1000000000000 AND timestamp >= ?)
                  )
                """,
                (user_id, cutoff_ts, cutoff_ms),
            )
            return cursor.fetchone()[0]

    def _get_team_snapshot_count_for_day(self, team_id: str, days_ago: int) -> int:
        """Get snapshot count for entire team for a specific day N days ago."""
        target_date = datetime.utcnow() - timedelta(days=days_ago)
        day_start_ts = int(target_date.replace(hour=0, minute=0, second=0).timestamp())
        day_end_ts = int(target_date.replace(hour=23, minute=59, second=59).timestamp())
        day_start_ms = day_start_ts * 1000
        day_end_ms = day_end_ts * 1000
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM synced_snapshots
                WHERE team_id = ?
                  AND (
                    (timestamp < 1000000000000 AND timestamp BETWEEN ? AND ?)
                    OR (timestamp >= 1000000000000 AND timestamp BETWEEN ? AND ?)
                  )
                """,
                (team_id, day_start_ts, day_end_ts, day_start_ms, day_end_ms),
            )
            return cursor.fetchone()[0]

    def _get_snapshot_count_for_day(self, user_id: str, team_id: str, days_ago: int) -> int:
        """Get snapshot count for a user in a team for a specific day N days ago."""
        target_date = datetime.utcnow() - timedelta(days=days_ago)
        day_start_ts = int(target_date.replace(hour=0, minute=0, second=0).timestamp())
        day_end_ts = int(target_date.replace(hour=23, minute=59, second=59).timestamp())
        day_start_ms = day_start_ts * 1000
        day_end_ms = day_end_ts * 1000

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM synced_snapshots
                WHERE user_id = ? AND team_id = ?
                  AND (
                    (timestamp < 1000000000000 AND timestamp BETWEEN ? AND ?)
                    OR (timestamp >= 1000000000000 AND timestamp BETWEEN ? AND ?)
                  )
                """,
                (user_id, team_id, day_start_ts, day_end_ts, day_start_ms, day_end_ms),
            )
            return cursor.fetchone()[0]

    def _get_user_snapshot_count_for_day(self, user_id: str, days_ago: int) -> int:
        """Get snapshot count for a user for a specific day N days ago."""
        target_date = datetime.utcnow() - timedelta(days=days_ago)
        day_start_ts = int(target_date.replace(hour=0, minute=0, second=0).timestamp())
        day_end_ts = int(target_date.replace(hour=23, minute=59, second=59).timestamp())
        day_start_ms = day_start_ts * 1000
        day_end_ms = day_end_ts * 1000
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM synced_snapshots
                WHERE user_id = ?
                  AND (
                    (timestamp < 1000000000000 AND timestamp BETWEEN ? AND ?)
                    OR (timestamp >= 1000000000000 AND timestamp BETWEEN ? AND ?)
                  )
                """,
                (user_id, day_start_ts, day_end_ts, day_start_ms, day_end_ms),
            )
            return cursor.fetchone()[0]
