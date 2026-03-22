from __future__ import annotations

import asyncio
from types import SimpleNamespace

from services.vector_db import VectorDBService


class _FakeCollection:
    def __init__(self) -> None:
        self.query_calls = 0
        self.get_calls = 0
        self.last_get_kwargs: dict | None = None
        self.upsert_calls = 0

    def count(self) -> int:
        return 3

    def query(self, **kwargs):
        self.query_calls += 1
        return {
            "metadatas": [[
                {"id": "1", "project_id": "p1", "timestamp": "2026-03-22T10:00:00+00:00"},
                {"id": "2", "project_id": "p1", "timestamp": "2026-03-22T09:00:00+00:00"},
            ]]
        }

    def get(self, **kwargs):
        self.get_calls += 1
        self.last_get_kwargs = kwargs
        return {
            "metadatas": [
                {"id": "older", "project_id": "p1", "timestamp": "2026-03-21T08:00:00+00:00"},
                {"id": "newer", "project_id": "p1", "timestamp": "2026-03-23T08:00:00+00:00"},
            ]
        }

    def upsert(self, **kwargs) -> None:
        self.upsert_calls += 1


async def _fixed_embedding(_: str) -> list[float]:
    return [0.1, 0.2, 0.3]


def test_semantic_search_uses_cache_for_repeated_query(monkeypatch):
    service = VectorDBService()
    collection = _FakeCollection()

    monkeypatch.setattr(service, "_get_collection", lambda _user_id=None: collection)
    monkeypatch.setattr(service, "generate_embedding", _fixed_embedding)

    first = asyncio.run(service.semantic_search("why is this slow", top_k=2, user_id="u1", project_id="p1"))
    second = asyncio.run(service.semantic_search("why is this slow", top_k=2, user_id="u1", project_id="p1"))

    assert len(first) == 2
    assert first == second
    assert collection.query_calls == 1


def test_get_recent_snapshots_pushes_project_filter_to_chroma(monkeypatch):
    service = VectorDBService()
    collection = _FakeCollection()

    monkeypatch.setattr(service, "_get_collection", lambda _user_id=None: collection)

    results = asyncio.run(service.get_recent_snapshots(limit=2, user_id="u1", project_id="p1"))

    assert collection.last_get_kwargs is not None
    assert collection.last_get_kwargs.get("where") == {"project_id": "p1"}
    assert results[0]["id"] == "newer"
    assert results[1]["id"] == "older"


def test_upsert_snapshot_clears_user_cache(monkeypatch):
    service = VectorDBService()
    collection = _FakeCollection()
    monkeypatch.setattr(service, "_get_collection", lambda _user_id=None: collection)

    cache_key = service._cache_key("timeline", "u1", "p1", 200)
    service._cache_set(cache_key, [{"id": "cached"}])
    assert service._cache_get(cache_key) is not None

    snapshot = SimpleNamespace(
        id="s-1",
        timestamp="2026-03-23T10:00:00+00:00",
        workspace_folder="repo",
        active_file="main.py",
        language_id="python",
        shadow_graph="def run(): pass",
        git_branch="main",
        project_id="p1",
        terminal_commands=[],
        metadata=SimpleNamespace(summary="summary", entities=[]),
        function_context={},
        embedding=[0.1, 0.2, 0.3],
    )

    asyncio.run(service.upsert_snapshot(snapshot, user_id="u1"))

    assert collection.upsert_calls == 1
    assert service._cache_get(cache_key) is None
