#!/usr/bin/env python3
"""
Tests for MCP PRD feature builders.

These tests validate tool behavior without requiring a running MCP host or
live Chroma service.
"""

from __future__ import annotations

from MCP import server


def _snapshot(sample_id: str, summary: str, entities: str, terminal_commands: str, confidence: float = 0.9) -> dict:
    return {
        "id": sample_id,
        "active_file": f"{sample_id}.py",
        "summary": summary,
        "entities": entities,
        "terminal_commands": terminal_commands,
        "timestamp": "2026-04-01T10:00:00+00:00",
        "confidence_score": confidence,
    }


def test_classify_logic_error_failures():
    sample = _snapshot(
        "snap-1",
        "TypeError thrown because a null value reached the auth path",
        "auth,bug,exception",
        '["pytest test_auth.py"]',
    )
    normalized = server._normalize_snapshot(sample, "test-collection")
    assert "logic_error" in server._classify_failure(normalized)


def test_self_improving_report_prefers_success_patterns():
    samples = [
        server._normalize_snapshot(
            _snapshot(
                "failed-1",
                "TypeError thrown in payment workflow due to missing guard.",
                "timeout,bug,payment",
                '["pytest test_payment.py"]',
            ),
            "test-collection",
        ),
        server._normalize_snapshot(
            _snapshot(
                "success-1",
                "Implemented retry backoff and validated with passing tests.",
                "retry,backoff,success",
                '["pytest test_retry.py"]',
            ),
            "test-collection",
        ),
    ]
    report = server._build_self_improving_report(
        task="fix payment flow retry bug",
        latest_outcome="failed with error",
        snapshots=samples,
    )
    assert report["feature"] == "self_improving_loop"
    assert report["failed_attempts"] == 1
    assert report["successful_attempts"] == 1
    assert any("Prefer validated strategies" in item for item in report["suggested_next_strategy"])


def test_failure_memory_groups_categories():
    samples = [
        server._normalize_snapshot(
            _snapshot(
                "fail-1",
                "Timeout observed when connecting to cache service",
                "cache,timeout,performance",
                '["npm test"]',
                confidence=0.9,
            ),
            "test-collection",
        ),
        server._normalize_snapshot(
            _snapshot(
                "fail-2",
                "Null pointer exception in parser",
                "parser,logic,bug",
                '["npm test"]',
                confidence=0.8,
            ),
            "test-collection",
        ),
    ]
    report = server._build_failure_memory_report(task="cache timeout", snapshots=samples, min_confidence=0.4)
    assert report["feature"] == "failure_aware_memory"
    assert report["failure_count"] == 2
    assert "performance_issue" in report["category_counts"]
    assert "logic_error" in report["category_counts"]


def test_proof_carrying_report_allows_supported_claim():
    snapshots = [
        server._normalize_snapshot(
            _snapshot(
                "support-1",
                "Use Redis cache for session state after fixing missing connection pool.",
                "redis,cache,sessions,success",
                '["npm run test"]',
                confidence=0.9,
            ),
            "test-collection",
        ),
        server._normalize_snapshot(
            _snapshot(
                "contradict-1",
                "Timeout failures during cache setup due to misconfiguration.",
                "cache,timeout,performance",
                '["npm run test"]',
                confidence=0.7,
            ),
            "test-collection",
        ),
    ]

    report = server._build_proof_carrying_report(
        response_text="Use Redis for session caching.",
        snapshots=snapshots,
    )
    assert report["feature"] == "proof_carrying_response"
    assert report["claim_count"] == 1
    assert report["overall_decision"] in {"allow", "revise"}
    assert report["checks"][0]["claim"] == "Use Redis for session caching."
