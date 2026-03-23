from __future__ import annotations

from datetime import datetime, timedelta, timezone

from main import _parse_iso_timestamp, _paths_match, _snapshot_mentions_symbol


def test_paths_match_handles_absolute_and_relative_forms() -> None:
    assert _paths_match("src/components/Dashboard.tsx", "C:/Users/me/repo/src/components/Dashboard.tsx")
    assert _paths_match("src\\utils\\file.py", "src/utils/file.py")
    assert not _paths_match("src/a.py", "src/b.py")


def test_snapshot_mentions_symbol_uses_structured_function_metadata() -> None:
    snapshot = {
        "active_symbol": "fetchSummary",
        "function_signatures": '["async function fetchSummary()", "function helper()"]',
        "summary": "Updated dashboard logic",
        "shadow_graph": "",
        "entities": "",
    }

    assert _snapshot_mentions_symbol(snapshot, "fetchSummary")
    assert _snapshot_mentions_symbol(snapshot, "helper")
    assert not _snapshot_mentions_symbol(snapshot, "otherSymbol")


def test_parse_iso_timestamp_returns_aware_utc_for_comparisons() -> None:
    snapshot_ts = _parse_iso_timestamp("2026-03-22T15:29:11.6505872Z")
    assert snapshot_ts is not None
    assert snapshot_ts.tzinfo is not None

    request_ts = datetime(2026, 3, 22, 15, 29, 11, tzinfo=timezone.utc)
    window_start = request_ts - timedelta(hours=2)
    window_end = request_ts + timedelta(hours=1)

    assert window_start <= snapshot_ts <= window_end
