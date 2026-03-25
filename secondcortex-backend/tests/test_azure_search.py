from services.azure_search import AzureSearchService
import asyncio


class _FakeResult:
    def __init__(self, succeeded: bool):
        self.succeeded = succeeded


class _FakeClient:
    def __init__(self):
        self.uploaded = []

    def search(self, **_kwargs):
        return [
            {
                "id": "s1",
                "summary": "timeout fixed",
                "active_file": "vector_db.py",
                "project_id": "p1",
                "timestamp": "2026-03-25T12:00:00+00:00",
                "git_branch": "main",
                "entities": "performance,bug_fix",
                "@search.score": 0.98,
            }
        ]

    def upload_documents(self, docs):
        self.uploaded.extend(docs)
        return [_FakeResult(True)]


def _service_with_fake_client() -> AzureSearchService:
    service = AzureSearchService.__new__(AzureSearchService)
    service.client = _FakeClient()
    service.endpoint = "https://example.search.windows.net"
    service.index_name = "snapshots"
    return service


def test_vector_search_returns_normalized_payload():
    service = _service_with_fake_client()

    results = asyncio.run(
        service.vector_search(
            query_vector=[0.1, 0.2, 0.3],
            user_id="u1",
            project_id="p1",
            k=5,
        )
    )

    assert len(results) == 1
    assert results[0]["id"] == "s1"
    assert results[0]["score"] == 0.98


def test_index_snapshot_success():
    service = _service_with_fake_client()

    ok = asyncio.run(service.index_snapshot({"id": "s2", "summary": "hello"}))

    assert ok is True
    assert service.client.uploaded[0]["id"] == "s2"
