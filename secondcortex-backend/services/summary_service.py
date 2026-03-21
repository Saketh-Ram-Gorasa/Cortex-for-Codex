"""
Plug-and-play summary generation service for teams.
Generates daily/weekly summaries that can be consumed by multiple dashboards.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from config import settings
from models.schemas import TeamDailySummary, TeamWeeklySummary, MemberSummary
from auth.database import UserDB

logger = logging.getLogger("secondcortex.services.summary_service")


class SummaryService:
    """Generate reusable team and individual summaries."""

    def __init__(self):
        self.db_path = str(Path(settings.chroma_db_path).parent / "auth.db")
        self.user_db = UserDB()

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
        
        for member in members:
            user_id = member["id"]
            
            # Get snapshot count for today
            snapshot_count = self._get_snapshot_count_for_day(user_id, team_id, days_ago=0)
            
            # Get commits for today
            commit_count = self._get_commit_count(user_id, days=1)
            
            # Get languages used today
            languages = self._get_languages_used(user_id, days=1)
            
            # Get files modified today
            files_modified = self._get_files_modified(user_id, days=1)
            
            is_active = snapshot_count > 0 or commit_count > 0
            if is_active:
                active_members += 1
            
            total_snapshots += snapshot_count
            total_commits += commit_count
            
            member_summaries.append(
                MemberSummary(
                    user_id=user_id,
                    display_name=member["display_name"],
                    email=member["email"],
                    snapshots_count=snapshot_count,
                    commits_count=commit_count,
                    languages_used=languages,
                    files_modified=files_modified,
                    status="active" if is_active else "idle",
                )
            )
        
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
        
        for member in members:
            user_id = member["id"]
            
            # Get snapshot count for this week
            snapshot_count = self._get_snapshot_count(user_id, team_id, days=7)
            
            # Get commits for this week
            commit_count = self._get_commit_count(user_id, days=7)
            
            # Get languages used this week
            languages = self._get_languages_used(user_id, days=7)
            
            # Get files modified this week
            files_modified = self._get_files_modified(user_id, days=7)
            
            is_active = snapshot_count > 0 or commit_count > 0
            if is_active:
                active_members += 1
            
            total_snapshots += snapshot_count
            total_commits += commit_count
            
            member_summaries.append(
                MemberSummary(
                    user_id=user_id,
                    display_name=member["display_name"],
                    email=member["email"],
                    snapshots_count=snapshot_count,
                    commits_count=commit_count,
                    languages_used=languages,
                    files_modified=files_modified,
                    status="active" if is_active else "idle",
                )
            )
        
        # Build daily breakdown for the week
        for i in range(7):
            day = (datetime.utcnow() - timedelta(days=i)).strftime("%A")
            count = self._get_team_snapshot_count_for_day(team_id, i)
            daily_breakdown[day] = count
        
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

    def generate_user_daily_summary(self, user_id: str) -> dict:
        """
        Generate a daily summary for an individual user.
        Returns dict compatible with summary response format with single-member array.
        """
        user = self.user_db.get_user_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        team_id = user.get("team_id")
        
        # Get snapshot count for today
        snapshot_count = self._get_user_snapshot_count_for_day(user_id, days_ago=0)
        
        # Get commits for today
        commit_count = self._get_commit_count(user_id, days=1)
        
        # Get languages used today
        languages = self._get_languages_used(user_id, days=1)
        
        # Get files modified today
        files_modified = self._get_files_modified(user_id, days=1)
        
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
        
        team_id = user.get("team_id")
        
        # Get snapshot count for this week
        snapshot_count = self._get_user_snapshot_count(user_id, days=7)
        
        # Get commits for this week
        commit_count = self._get_commit_count(user_id, days=7)
        
        # Get languages used this week
        languages = self._get_languages_used(user_id, days=7)
        
        # Get files modified this week
        files_modified = self._get_files_modified(user_id, days=7)
        
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
            day = (datetime.utcnow() - timedelta(days=i)).strftime("%A")
            count = self._get_user_snapshot_count_for_day(user_id, i)
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
