from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import codexcortex_mcp as cortex


class FakeUserDB:
    def get_user_by_mcp_api_key(self, api_key: str):
        if api_key == "valid-key":
            return {"id": "user-1", "display_name": "Codex User"}
        return None


class FakeVectorDB:
    def __init__(self):
        self.chroma_client = object()
        self.semantic_results = [
            {
                "id": "snap-1",
                "timestamp": "2026-04-16T10:00:00+00:00",
                "active_file": "src/auth/middleware.py",
                "git_branch": "main",
                "summary": "Moved token refresh into middleware to avoid duplicate DB calls.",
                "entities": "auth,token_refresh,middleware",
                "confidence_score": 0.91,
            }
        ]
        self.timeline_results = []
        self.upserted = []

    def _get_collection(self, user_id: str | None = None):
        return object() if user_id else None

    async def semantic_search(self, query: str, top_k: int = 5, user_id: str | None = None):
        return self.semantic_results[:top_k]

    async def get_snapshot_timeline(self, limit: int = 200, user_id: str | None = None):
        return self.timeline_results[:limit]

    async def upsert_external_record(self, record, user_id: str | None = None):
        self.upserted.append((record, user_id))
        return record.source_id


class CodexCortexToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake_vector = FakeVectorDB()
        self.user_patch = patch.object(cortex, "user_db", FakeUserDB())
        self.vector_patch = patch.object(cortex, "vector_db", self.fake_vector)
        self.user_patch.start()
        self.vector_patch.start()
        self.env_patch = patch.dict(os.environ, {"SECONDCORTEX_MCP_API_KEY": "valid-key"})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.vector_patch.stop()
        self.user_patch.stop()

    async def test_tools_auth_failure(self):
        with patch.dict(os.environ, {}, clear=True):
            checks = [
                await cortex.search_memory(query="auth", api_key=None),
                await cortex.get_decision_context(target="auth.py", api_key=None),
                await cortex.list_snapshots(api_key=None),
                await cortex.store_decision(
                    task_prompt="fix auth",
                    reasoning="used existing middleware",
                    files_modified=["src/auth.py"],
                    api_key=None,
                ),
                await cortex.get_mcp_readiness(api_key=None),
            ]

        self.assertIn("Authentication required", checks[0])
        self.assertIn("Authentication required", checks[1])
        self.assertIn("Authentication required", checks[2])
        self.assertIn("Authentication required", checks[3])
        self.assertIn("not-ready", checks[4])

    async def test_search_memory_success(self):
        output = await cortex.search_memory(query="auth token refresh")

        self.assertIn("Found 1 memory result", output)
        self.assertIn("src/auth/middleware.py", output)
        self.assertIn("Confidence: 0.91", output)

    async def test_get_decision_context_success_and_empty(self):
        self.fake_vector.semantic_results[0]["source_type"] = "codex_decision"
        self.fake_vector.semantic_results[0]["shadow_graph"] = (
            '{"task_prompt":"Fix auth refresh","files_modified":["src/auth/middleware.py"],'
            '"tags":["auth"],"parent_snapshot_id":"parent-123","contradictions":""}'
        )
        output = await cortex.get_decision_context(target="TokenRefreshMiddleware", depth=2)
        self.assertIn("Decision context for 'TokenRefreshMiddleware'", output)
        self.assertIn("snap-1", output)
        self.assertIn("Parent: parent-123", output)
        self.assertIn("Files modified: src/auth/middleware.py", output)

        self.fake_vector.semantic_results = []
        empty = await cortex.get_decision_context(target="missing")
        self.assertIn("No decision context found", empty)

    async def test_list_snapshots_filters_file_and_recency(self):
        now = datetime.now(timezone.utc)
        self.fake_vector.timeline_results = [
            {
                "id": "recent-auth",
                "timestamp": (now - timedelta(hours=2)).isoformat(),
                "active_file": "src/auth/middleware.py",
                "git_branch": "main",
                "summary": "Recent auth work",
            },
            {
                "id": "recent-payments",
                "timestamp": (now - timedelta(hours=2)).isoformat(),
                "active_file": "src/payments/service.py",
                "git_branch": "main",
                "summary": "Recent payment work",
            },
            {
                "id": "old-auth",
                "timestamp": (now - timedelta(hours=200)).isoformat(),
                "active_file": "src/auth/middleware.py",
                "git_branch": "main",
                "summary": "Old auth work",
            },
        ]

        output = await cortex.list_snapshots(file_path="src/auth/middleware.py", limit=5, since_hours=24)

        self.assertIn("recent-auth", output)
        self.assertNotIn("recent-payments", output)
        self.assertNotIn("old-auth", output)

    async def test_store_decision_validates_and_persists(self):
        invalid = await cortex.store_decision(
            task_prompt="fix auth",
            reasoning="",
            files_modified=["src/auth.py"],
        )
        self.assertIn("reasoning is required", invalid)

        output = await cortex.store_decision(
            task_prompt="Fix auth refresh",
            reasoning="Kept token refresh in middleware because prior memory says it avoids duplicate DB calls.",
            files_modified=["src/auth/middleware.py"],
            confidence=1.7,
            tags=["Auth", "token refresh"],
            parent_snapshot_id="snap-1",
            contradictions="",
        )

        self.assertIn("Codex decision stored successfully", output)
        self.assertIn("Confidence: 1.00", output)
        self.assertEqual(len(self.fake_vector.upserted), 1)

        record, user_id = self.fake_vector.upserted[0]
        self.assertEqual(user_id, "user-1")
        self.assertEqual(record.source_type, "codex_decision")
        self.assertEqual(record.confidence_score, 1.0)
        self.assertIn("src/auth/middleware.py", record.content)
        self.assertIn("snap-1", record.content)

    async def test_readiness_success(self):
        output = await cortex.get_mcp_readiness()

        self.assertIn("CodexCortex readiness: READY", output)
        self.assertIn("auth: ok", output)
        self.assertIn("vector_collection: ok", output)

    def test_main_uses_anyio_run_for_console_entry_point(self):
        with patch.object(cortex.logger, "info") as mock_logger_info, patch.object(
            cortex.anyio, "run"
        ) as mock_anyio_run:
            cortex.main()

        mock_logger_info.assert_called_once_with("Starting CodexCortex MCP server via stdio.")
        mock_anyio_run.assert_called_once_with(cortex._run_mcp_compat_stdio)


if __name__ == "__main__":
    unittest.main()
