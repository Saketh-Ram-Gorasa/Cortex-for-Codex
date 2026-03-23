from __future__ import annotations

import asyncio

from agents.planner import PlannerAgent, _extract_requested_snapshot_count


class _FakeVectorDB:
    def __init__(self) -> None:
        self.timeline_calls: list[int] = []
        self.semantic_calls: list[str] = []

    async def get_snapshot_timeline(self, limit: int, user_id: str | None = None):
        self.timeline_calls.append(limit)
        return [
            {"id": "s1", "active_file": "a.py", "git_branch": "main", "timestamp": "2026-03-20T10:00:00+00:00", "summary": "Edited a"},
            {"id": "s2", "active_file": "b.py", "git_branch": "main", "timestamp": "2026-03-20T09:00:00+00:00", "summary": "Edited b"},
            {"id": "s3", "active_file": "c.py", "git_branch": "main", "timestamp": "2026-03-20T08:00:00+00:00", "summary": "Edited c"},
        ][:limit]

    async def semantic_search(self, query: str, top_k: int = 5, user_id: str | None = None):
        self.semantic_calls.append(query)
        return [{"id": "sem1", "summary": "semantic result"}]


class _PartiallyFailingVectorDB(_FakeVectorDB):
    async def semantic_search(self, query: str, top_k: int = 5, user_id: str | None = None):
        self.semantic_calls.append(query)
        if "fail" in query:
            raise RuntimeError("simulated semantic failure")
        return [{"id": "sem-ok", "summary": f"result for {query}"}]


def test_extract_requested_snapshot_count_parses_numbers():
    assert _extract_requested_snapshot_count("fetch me 3 latest snapshots") == 3
    assert _extract_requested_snapshot_count("latest 7 snapshots") == 7
    assert _extract_requested_snapshot_count("latest snapshots") == 3
    assert _extract_requested_snapshot_count("latest snapshot") == 1


def test_planner_uses_timeline_for_latest_snapshot_requests():
    db = _FakeVectorDB()
    agent = PlannerAgent(db)

    result = asyncio.run(agent.plan("can fetch me 3 latest snapshots?", user_id="u1"))

    assert db.timeline_calls == [3]
    assert db.semantic_calls == []
    assert len(result.retrieved_context) == 3
    assert result.search_queries == ["latest_3_snapshots"]


def test_planner_keeps_successful_results_when_one_semantic_query_fails():
    db = _PartiallyFailingVectorDB()
    agent = PlannerAgent(db)

    async def fake_generate_plan(_question: str):
        return {
            "intent": "mixed query",
            "search_queries": ["good query", "fail query"],
            "temporal_scope": "all_time",
        }

    agent._generate_plan = fake_generate_plan  # type: ignore[method-assign]

    result = asyncio.run(agent.plan("mixed", user_id="u1"))

    assert db.semantic_calls == ["good query", "fail query"]
    assert len(result.retrieved_context) == 1
    assert result.retrieved_context[0]["id"] == "sem-ok"