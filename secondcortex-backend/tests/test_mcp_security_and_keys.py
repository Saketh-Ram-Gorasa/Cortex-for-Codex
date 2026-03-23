from __future__ import annotations

import asyncio
import uuid

from fastapi.testclient import TestClient

import mcp_server
from auth.database import UserDB


def test_userdb_issue_lookup_and_revoke_mcp_key(monkeypatch, tmp_path):
    monkeypatch.setattr("auth.database.settings.chroma_db_path", str(tmp_path / "chroma_db"))

    db = UserDB()
    email = f"mcp-{uuid.uuid4().hex[:8]}@example.com"
    user = db.create_user(email, "test123", "MCP User")
    assert user is not None

    issued = db.issue_mcp_api_key(user_id=user["id"], name="claude-desktop", scopes=["memory:read"], ttl_days=7)
    assert issued["api_key"].startswith("sc_mcp_")
    assert issued["key_id"]

    looked_up = db.get_user_by_mcp_api_key(issued["api_key"])
    assert looked_up is not None
    assert looked_up["id"] == user["id"]
    assert "memory:read" in looked_up.get("scopes", [])

    revoked = db.revoke_mcp_api_key(user_id=user["id"], key_id=issued["key_id"])
    assert revoked is True
    assert db.get_user_by_mcp_api_key(issued["api_key"]) is None


def test_mcp_server_search_memory_requires_key_and_validates_query(monkeypatch):
    async def run_empty_query():
        return await mcp_server.search_memory(query="", api_key=None, top_k=5)

    async def run_missing_key():
        return await mcp_server.search_memory(query="auth flow", api_key=None, top_k=5)

    result_empty = asyncio.run(run_empty_query())
    assert "query must be non-empty" in result_empty

    monkeypatch.delenv("SECONDCORTEX_MCP_API_KEY", raising=False)
    result_missing_key = asyncio.run(run_missing_key())
    assert "Authentication required" in result_missing_key


def test_mcp_keys_routes_issue_list_revoke():
    from main import app

    client = TestClient(app)

    email = f"routes-{uuid.uuid4().hex[:8]}@example.com"
    signup = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "test123", "display_name": "Routes User"},
    )
    assert signup.status_code == 200
    token = signup.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    issue = client.post(
        "/api/v1/auth/mcp-keys",
        headers=headers,
        json={"name": "cursor", "scopes": ["memory:read"], "ttl_days": 30},
    )
    assert issue.status_code == 200
    issued = issue.json()
    assert issued["api_key"].startswith("sc_mcp_")
    assert issued["key_id"]

    listing = client.get("/api/v1/auth/mcp-keys", headers=headers)
    assert listing.status_code == 200
    keys = listing.json()["keys"]
    assert any(key["key_id"] == issued["key_id"] for key in keys)

    revoke = client.delete(f"/api/v1/auth/mcp-keys/{issued['key_id']}", headers=headers)
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "revoked"


def test_hierarchical_mcp_tools_return_context(monkeypatch):
    class _FakeUserDB:
        def get_user_by_mcp_api_key(self, api_key: str):
            if api_key == "test-key":
                return {"id": "u1", "display_name": "User 1", "scopes": ["memory:read"]}
            return None

    class _FakeVectorDB:
        async def semantic_search(self, query: str, top_k: int = 5, user_id: str | None = None, project_id: str | None = None):
            return [
                {
                    "timestamp": "2026-03-23T10:00:00+00:00",
                    "active_file": "payment.ts",
                    "git_branch": "feature/payment-fix",
                    "summary": f"Worked on {query}",
                    "entities": "processPayment,validateCard,rollback",
                    "active_symbol": "processPayment",
                    "shadow_graph": "function processPayment() { return validateCard(); }",
                }
            ][:top_k]

        async def get_snapshot_timeline(self, limit: int = 200, user_id: str | None = None, project_id: str | None = None):
            return [
                {
                    "timestamp": "2026-03-23T10:00:00+00:00",
                    "active_file": "payment.ts",
                    "git_branch": "feature/payment-fix",
                    "summary": "Investigated payment rollback",
                    "entities": "processPayment,validateCard",
                },
                {
                    "timestamp": "2026-03-23T09:00:00+00:00",
                    "active_file": "db.ts",
                    "git_branch": "feature/payment-fix",
                    "summary": "Optimized DB retries",
                    "entities": "db,retry",
                },
            ][:limit]

    monkeypatch.setenv("SECONDCORTEX_MCP_API_KEY", "test-key")
    monkeypatch.setattr(mcp_server, "user_db", _FakeUserDB())
    monkeypatch.setattr(mcp_server, "vector_db", _FakeVectorDB())
    mcp_server._rate_limiter._calls.clear()

    overview = asyncio.run(mcp_server.get_codebase_overview())
    assert "Codebase overview" in overview

    domain_context = asyncio.run(mcp_server.get_domain_context(domain="payment-service"))
    assert "Domain context for 'payment-service'" in domain_context

    function_context = asyncio.run(mcp_server.get_function_context(file="payment.ts", function="processPayment"))
    assert "Function context for processPayment in payment.ts" in function_context

    raw = asyncio.run(mcp_server.get_raw_snapshots(query="payment rollback", max_tokens=500))
    assert "Raw snapshots for 'payment rollback'" in raw


def test_get_related_context_co_changed_and_depth(monkeypatch):
    class _FakeUserDB:
        def get_user_by_mcp_api_key(self, api_key: str):
            if api_key == "graph-key":
                return {"id": 1, "display_name": "Graph User", "scopes": ["memory:read"]}
            return None

    graph_snapshots = [
        {
            "summary": "Edited retriever and planner for better context windows",
            "entities": ["retriever.py", "planner.py"],
            "timestamp": "2026-03-20T10:00:00Z",
            "active_symbol": "retrieve_context",
        },
        {
            "summary": "Planner and executor adjusted after failing integration tests",
            "entities": ["planner.py", "executor.py"],
            "timestamp": "2026-03-21T12:00:00Z",
            "active_symbol": "run_plan",
        },
        {
            "summary": "Executor and validator updated for handoff stability",
            "entities": ["executor.py", "validator.py"],
            "timestamp": "2026-03-22T13:00:00Z",
            "active_symbol": "validate_step",
        },
    ]

    async def fake_semantic(query, top_k, user_id):
        assert user_id == 1
        return graph_snapshots

    monkeypatch.setenv("SECONDCORTEX_MCP_API_KEY", "graph-key")
    monkeypatch.setattr(mcp_server, "user_db", _FakeUserDB())
    monkeypatch.setattr(mcp_server.vector_db, "semantic_search", fake_semantic)
    mcp_server._rate_limiter._calls.clear()

    response = asyncio.run(
        mcp_server.get_related_context(
            anchor="planner.py",
            relationship_types=["co-changed"],
            api_key=None,
            depth=2,
            top_k=6,
        )
    )

    assert "Related context for 'planner.py'" in response
    assert "Level 1 from planner.py" in response
    assert "retriever.py [co-changed]" in response or "executor.py [co-changed]" in response
    assert "Discovered nodes:" in response


def test_get_related_context_budget_truncates(monkeypatch):
    class _FakeUserDB:
        def get_user_by_mcp_api_key(self, api_key: str):
            if api_key == "graph-budget-key":
                return {"id": 1, "display_name": "Graph User", "scopes": ["memory:read"]}
            return None

    graph_snapshots = [
        {
            "summary": "A" * 500,
            "entities": ["anchor.py", "neighbor_a.py", "neighbor_b.py", "neighbor_c.py"],
            "timestamp": "2026-03-20T10:00:00Z",
            "active_symbol": "anchor_symbol",
        }
    ]

    async def fake_semantic(query, top_k, user_id):
        return graph_snapshots

    monkeypatch.setenv("SECONDCORTEX_MCP_API_KEY", "graph-budget-key")
    monkeypatch.setattr(mcp_server, "user_db", _FakeUserDB())
    monkeypatch.setattr(mcp_server.vector_db, "semantic_search", fake_semantic)
    mcp_server._rate_limiter._calls.clear()

    response = asyncio.run(
        mcp_server.get_related_context(
            anchor="anchor.py",
            api_key=None,
            depth=3,
            max_tokens=120,
            top_k=8,
        )
    )

    assert "Related context for 'anchor.py'" in response
    assert "Traversal truncated due to token budget" in response or "Discovered nodes:" in response


def test_search_memory_remains_compatible_with_legacy_api_key_arg(monkeypatch):
    class _FakeUserDB:
        def get_user_by_mcp_api_key(self, api_key: str):
            if api_key == "legacy-key":
                return {"id": "u1", "display_name": "User 1", "scopes": ["memory:read"]}
            return None

    class _FakeVectorDB:
        async def semantic_search(self, query: str, top_k: int = 5, user_id: str | None = None, project_id: str | None = None):
            return [{"timestamp": "now", "active_file": "a.py", "git_branch": "main", "summary": "ok", "entities": "x"}]

    monkeypatch.setattr(mcp_server, "user_db", _FakeUserDB())
    monkeypatch.setattr(mcp_server, "vector_db", _FakeVectorDB())
    monkeypatch.setattr(mcp_server.settings, "mcp_legacy_tool_api_key_enabled", True)
    mcp_server._rate_limiter._calls.clear()

    out = asyncio.run(mcp_server.search_memory(query="hello", api_key="legacy-key", top_k=3))
    assert "Found 1 relevant snapshots" in out


def test_get_context_for_task_type_validates_task_type(monkeypatch):
    class _FakeUserDB:
        def get_user_by_mcp_api_key(self, api_key: str):
            if api_key == "task-key":
                return {"id": "u1", "display_name": "User 1", "scopes": ["memory:read"]}
            return None

    monkeypatch.setenv("SECONDCORTEX_MCP_API_KEY", "task-key")
    monkeypatch.setattr(mcp_server, "user_db", _FakeUserDB())
    mcp_server._rate_limiter._calls.clear()

    out = asyncio.run(
        mcp_server.get_context_for_task_type(
            domain="auth",
            task_type="planning",
            api_key=None,
        )
    )
    assert "task_type must be one of" in out


def test_get_context_for_task_type_cache_hit_and_stale_rebuild(monkeypatch):
    class _FakeUserDB:
        def get_user_by_mcp_api_key(self, api_key: str):
            if api_key == "task-cache-key":
                return {"id": "u1", "display_name": "User 1", "scopes": ["memory:read"]}
            return None

    snapshots_by_call = [
        [
            {
                "timestamp": "2026-03-23T10:00:00Z",
                "active_file": "auth/routes.py",
                "git_branch": "feature/auth",
                "summary": "Fixed login redirect loop",
                "entities": "login,session,jwt",
            }
        ],
        [
            {
                "timestamp": "2026-03-23T10:00:00Z",
                "active_file": "auth/routes.py",
                "git_branch": "feature/auth",
                "summary": "Fixed login redirect loop",
                "entities": "login,session,jwt",
            }
        ],
        [
            {
                "timestamp": "2026-03-23T12:00:00Z",
                "active_file": "auth/jwt_handler.py",
                "git_branch": "feature/auth",
                "summary": "Patched token refresh race condition",
                "entities": "token,refresh,jwt",
            }
        ],
    ]
    call_counter = {"index": 0}

    async def fake_semantic(query, top_k, user_id, project_id=None):
        idx = min(call_counter["index"], len(snapshots_by_call) - 1)
        call_counter["index"] += 1
        return snapshots_by_call[idx]

    monkeypatch.setenv("SECONDCORTEX_MCP_API_KEY", "task-cache-key")
    monkeypatch.setattr(mcp_server, "user_db", _FakeUserDB())
    monkeypatch.setattr(mcp_server.vector_db, "semantic_search", fake_semantic)
    monkeypatch.setattr(mcp_server.settings, "mcp_task_summary_cache_enabled", True)
    monkeypatch.setattr(mcp_server.settings, "mcp_task_summary_ttl_seconds", 3600)
    mcp_server._rate_limiter._calls.clear()
    mcp_server._task_summary_cache.clear()

    first = asyncio.run(
        mcp_server.get_context_for_task_type(
            domain="auth",
            task_type="debugging",
            api_key=None,
            top_k=4,
        )
    )
    assert "cache_status=MISS" in first

    second = asyncio.run(
        mcp_server.get_context_for_task_type(
            domain="auth",
            task_type="debugging",
            api_key=None,
            top_k=4,
        )
    )
    assert "cache_status=HIT" in second

    third = asyncio.run(
        mcp_server.get_context_for_task_type(
            domain="auth",
            task_type="debugging",
            api_key=None,
            top_k=4,
        )
    )
    assert "cache_status=STALE_REBUILT" in third


def test_ingest_slack_thread_respects_feature_flags(monkeypatch):
    class _FakeUserDB:
        def get_user_by_mcp_api_key(self, api_key: str):
            if api_key == "slack-key":
                return {"id": "u1", "display_name": "User 1", "scopes": ["memory:read"]}
            return None

    monkeypatch.setenv("SECONDCORTEX_MCP_API_KEY", "slack-key")
    monkeypatch.setattr(mcp_server, "user_db", _FakeUserDB())
    monkeypatch.setattr(mcp_server.settings, "mcp_external_ingestion_enabled", True)
    monkeypatch.setattr(mcp_server.settings, "mcp_external_slack_enabled", False)
    mcp_server._rate_limiter._calls.clear()

    out = asyncio.run(
        mcp_server.ingest_slack_thread(
            channel="backend-alerts",
            thread_ts="171111.123",
            messages=["Error spike in auth service"],
            domain="auth",
            api_key=None,
        )
    )
    assert "Slack ingestion is disabled" in out


def test_ingest_slack_thread_persists_record(monkeypatch):
    class _FakeUserDB:
        def get_user_by_mcp_api_key(self, api_key: str):
            if api_key == "slack-key-ok":
                return {"id": "u1", "display_name": "User 1", "scopes": ["memory:read"]}
            return None

    captured = {"record": None, "user_id": None}

    async def fake_upsert_external_record(record, user_id=None):
        captured["record"] = record
        captured["user_id"] = user_id
        return "slack:backend-alerts:171111.123"

    monkeypatch.setenv("SECONDCORTEX_MCP_API_KEY", "slack-key-ok")
    monkeypatch.setattr(mcp_server, "user_db", _FakeUserDB())
    monkeypatch.setattr(mcp_server.vector_db, "upsert_external_record", fake_upsert_external_record)
    monkeypatch.setattr(mcp_server.settings, "mcp_external_ingestion_enabled", True)
    monkeypatch.setattr(mcp_server.settings, "mcp_external_slack_enabled", True)
    monkeypatch.setattr(mcp_server.settings, "mcp_external_max_messages", 10)
    mcp_server._rate_limiter._calls.clear()

    out = asyncio.run(
        mcp_server.ingest_slack_thread(
            channel="backend-alerts",
            thread_ts="171111.123",
            messages=["Auth service timeout", "Possible DB lock contention"],
            domain="auth",
            api_key=None,
        )
    )

    assert "Slack thread ingested successfully" in out
    assert captured["user_id"] == "u1"
    assert captured["record"] is not None
    assert captured["record"].source_type == "slack"


def test_search_memory_includes_lineage_and_confidence(monkeypatch):
    class _FakeUserDB:
        def get_user_by_mcp_api_key(self, api_key: str):
            if api_key == "lineage-key":
                return {"id": "u1", "display_name": "User 1", "scopes": ["memory:read"]}
            return None

    class _FakeVectorDB:
        async def semantic_search(self, query: str, top_k: int = 5, user_id: str | None = None, project_id: str | None = None):
            return [
                {
                    "timestamp": "2026-03-23T10:00:00+00:00",
                    "active_file": "Slack thread in #backend-alerts",
                    "git_branch": "external",
                    "summary": "Auth incident triage",
                    "entities": "auth,timeout,db",
                    "source_type": "slack",
                    "source_uri": "slack://backend-alerts/171111.123",
                    "confidence_score": 0.82,
                }
            ]

    monkeypatch.setenv("SECONDCORTEX_MCP_API_KEY", "lineage-key")
    monkeypatch.setattr(mcp_server, "user_db", _FakeUserDB())
    monkeypatch.setattr(mcp_server, "vector_db", _FakeVectorDB())
    mcp_server._rate_limiter._calls.clear()

    out = asyncio.run(mcp_server.search_memory(query="auth incident", api_key=None, top_k=3))
    assert "Source: slack" in out
    assert "Source URI: slack://backend-alerts/171111.123" in out
    assert "Confidence: 0.82" in out


def test_get_mcp_metrics_reports_latency_and_counters(monkeypatch):
    class _FakeUserDB:
        def get_user_by_mcp_api_key(self, api_key: str):
            if api_key == "metrics-key":
                return {"id": "u1", "display_name": "User 1", "scopes": ["memory:read"]}
            return None

    class _FakeVectorDB:
        async def semantic_search(self, query: str, top_k: int = 5, user_id: str | None = None, project_id: str | None = None):
            return [{"timestamp": "now", "active_file": "a.py", "git_branch": "main", "summary": "ok", "entities": "x"}]

    monkeypatch.setenv("SECONDCORTEX_MCP_API_KEY", "metrics-key")
    monkeypatch.setattr(mcp_server, "user_db", _FakeUserDB())
    monkeypatch.setattr(mcp_server, "vector_db", _FakeVectorDB())
    mcp_server._rate_limiter._calls.clear()

    mcp_server._mcp_metrics["requests_total"] = 0
    mcp_server._mcp_metrics["success_total"] = 0
    mcp_server._mcp_metrics["error_total"] = 0
    mcp_server._mcp_metrics["auth_failures"] = 0
    mcp_server._mcp_metrics["rate_limited"] = 0
    mcp_server._mcp_metrics["oversized_rejections"] = 0
    mcp_server._mcp_metrics["task_cache_hit"] = 0
    mcp_server._mcp_metrics["task_cache_miss"] = 0
    mcp_server._mcp_metrics["task_cache_stale_rebuilt"] = 0
    mcp_server._mcp_metrics["tool_counts"].clear()
    mcp_server._mcp_metrics["tool_latency_ms"].clear()
    mcp_server._mcp_metrics["graph_discovered_nodes"].clear()

    _ = asyncio.run(mcp_server.search_memory(query="hello", api_key=None, top_k=3))
    metrics = asyncio.run(mcp_server.get_mcp_metrics(api_key=None))

    assert "MCP Metrics:" in metrics
    assert "Requests total:" in metrics
    assert "Per-tool metrics:" in metrics
    assert "search_memory" in metrics


def test_get_mcp_readiness_reports_degraded_when_vector_unavailable(monkeypatch):
    class _FakeUserDB:
        def get_user_by_mcp_api_key(self, api_key: str):
            if api_key == "readiness-key":
                return {"id": "u1", "display_name": "User 1", "scopes": ["memory:read"]}
            return None

    class _FakeVectorDB:
        chroma_client = None

        def _get_collection(self, user_id=None):
            return None

    monkeypatch.setenv("SECONDCORTEX_MCP_API_KEY", "readiness-key")
    monkeypatch.setattr(mcp_server, "user_db", _FakeUserDB())
    monkeypatch.setattr(mcp_server, "vector_db", _FakeVectorDB())
    mcp_server._rate_limiter._calls.clear()

    out = asyncio.run(mcp_server.get_mcp_readiness(api_key=None))
    assert "MCP readiness: DEGRADED" in out
    assert "vector_client: not-ready" in out
