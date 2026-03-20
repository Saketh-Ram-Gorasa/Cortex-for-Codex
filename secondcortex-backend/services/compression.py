"""
Memory Compression Service — Auto-Summarization Layers

Compresses old snapshots into higher-level summaries:
  - Daily summaries
  - Weekly summaries
  - Feature-level summaries

This keeps the vector DB lean while preserving context quality.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Any

from services.llm_client import create_llm_client, get_chat_model
from services.rate_limiter import rate_limited_call

logger = logging.getLogger("secondcortex.compression")


# COMPRESSION_CONFLICT_MARKER_START: snapshot-context-compression
async def compress_memory(user_id: str, vector_db: Any) -> dict:
    """
    Summarize old snapshots into higher-level daily/weekly/feature chunks.
    Returns a report of what was compressed.
    """
    logger.info("Starting memory compression for user=%s", user_id)

    # Fetch all snapshots (up to 1000)
    all_snapshots = await vector_db.get_snapshot_timeline(limit=1000, user_id=user_id)

    if not all_snapshots:
        logger.info("No snapshots found for user=%s — nothing to compress.", user_id)
        return {"status": "empty", "compressed": 0}

    # ── Group snapshots by date ────────────────────────────────
    # COMPRESSION_CONFLICT_MARKER_START: group-by-date
    by_date: dict[str, list[dict]] = defaultdict(list)
    for snap in all_snapshots:
        ts = snap.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
        except (ValueError, TypeError):
            dt = None
        if dt:
            by_date[dt.strftime("%Y-%m-%d")].append(snap)
    # COMPRESSION_CONFLICT_MARKER_END: group-by-date

    llm = create_llm_client()
    model = get_chat_model()
    report = {"daily": [], "weekly": [], "feature": []}

    # ── Daily Summaries ────────────────────────────────────────
    # COMPRESSION_CONFLICT_MARKER_START: daily-compression
    cutoff = datetime.utcnow() - timedelta(days=1)

    for date_key, snapshots in sorted(by_date.items()):
        try:
            day_dt = datetime.strptime(date_key, "%Y-%m-%d")
        except ValueError:
            continue

        if day_dt >= cutoff:
            continue  # Skip today/recent — only compress older data

        summaries_text = "\n".join(
            f"- [{s.get('active_file', '?')}] ({s.get('language_id', '?')}): {s.get('summary', 'no summary')}"
            for s in snapshots
        )
        if not summaries_text.strip():
            continue

        prompt = (
            f"Summarize these developer activity snapshots from {date_key} into a concise daily summary "
            f"(2-3 sentences). Focus on what files were worked on, which languages, and the overall progress.\n\n"
            f"{summaries_text}"
        )

        try:
            resp = await rate_limited_call(
                llm.chat.completions.create,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            daily_summary = resp.choices[0].message.content.strip()
            report["daily"].append({"date": date_key, "count": len(snapshots), "summary": daily_summary})
            logger.info("Daily summary for %s: %s", date_key, daily_summary[:80])
        except Exception as exc:
            logger.error("Failed to generate daily summary for %s: %s", date_key, exc)

    # ── Weekly Summaries ───────────────────────────────────────
    # COMPRESSION_CONFLICT_MARKER_END: daily-compression
    # COMPRESSION_CONFLICT_MARKER_START: weekly-compression
    by_week: dict[str, list[dict]] = defaultdict(list)
    for snap in all_snapshots:
        ts = snap.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
        except (ValueError, TypeError):
            dt = None
        if dt:
            week_key = dt.strftime("%Y-W%W")
            by_week[week_key].append(snap)

    for week_key, snapshots in sorted(by_week.items()):
        if len(snapshots) < 3:
            continue  # Not enough data for a meaningful weekly summary

        summaries_text = "\n".join(
            f"- [{s.get('active_file', '?')}] {s.get('summary', 'no summary')}"
            for s in snapshots[:30]  # Cap to avoid token overflow
        )

        prompt = (
            f"Summarize the developer's weekly activity ({week_key}) into a brief weekly report "
            f"(3-4 sentences). Highlight key accomplishments, languages used, and patterns.\n\n"
            f"{summaries_text}"
        )

        try:
            resp = await rate_limited_call(
                llm.chat.completions.create,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=250,
            )
            weekly_summary = resp.choices[0].message.content.strip()
            report["weekly"].append({"week": week_key, "count": len(snapshots), "summary": weekly_summary})
            logger.info("Weekly summary for %s: %s", week_key, weekly_summary[:80])
        except Exception as exc:
            logger.error("Failed to generate weekly summary for %s: %s", week_key, exc)

    # ── Feature-Level Summaries ────────────────────────────────
    # COMPRESSION_CONFLICT_MARKER_END: weekly-compression
    # COMPRESSION_CONFLICT_MARKER_START: feature-compression
    by_file: dict[str, list[dict]] = defaultdict(list)
    for snap in all_snapshots:
        af = snap.get("active_file", "")
        if af:
            by_file[af].append(snap)

    for file_path, snapshots in by_file.items():
        if len(snapshots) < 2:
            continue  # Not enough data

        summaries_text = "\n".join(
            f"- [{s.get('timestamp', '?')}] {s.get('summary', 'no summary')}"
            for s in snapshots[:20]
        )

        prompt = (
            f"Summarize the work done on file '{file_path}' across these snapshots "
            f"into a feature-level summary (1-2 sentences).\n\n{summaries_text}"
        )

        try:
            resp = await rate_limited_call(
                llm.chat.completions.create,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
            )
            feature_summary = resp.choices[0].message.content.strip()
            report["feature"].append({"file": file_path, "count": len(snapshots), "summary": feature_summary})
            logger.info("Feature summary for %s: %s", file_path, feature_summary[:80])
        except Exception as exc:
            logger.error("Failed to generate feature summary for %s: %s", file_path, exc)

    # COMPRESSION_CONFLICT_MARKER_END: feature-compression
    total = len(report["daily"]) + len(report["weekly"]) + len(report["feature"])
    logger.info("Memory compression complete for user=%s. Generated %d summaries.", user_id, total)
    return {"status": "ok", "compressed": total, "report": report}
# COMPRESSION_CONFLICT_MARKER_END: snapshot-context-compression
