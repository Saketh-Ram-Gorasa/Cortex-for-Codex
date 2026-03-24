from services.vector_db import VectorDBService


class _BrokenCollection:
    def __init__(self, error_message: str):
        self.error_message = error_message

    def count(self):
        raise RuntimeError(self.error_message)


class _HealthyCollection:
    def __init__(self, metadatas: list[dict]):
        self._metadatas = metadatas

    def count(self):
        return len(self._metadatas)

    def get(self, **_kwargs):
        return {"metadatas": self._metadatas}


def test_get_snapshot_metadatas_recovers_from_compactor_failure(monkeypatch):
    service = VectorDBService()
    user_id = "u-compactor"

    broken = _BrokenCollection(
        "Error executing plan: Error sending backfill request to compactor: Failed to apply logs to the metadata segment"
    )
    healthy = _HealthyCollection(
        [{"timestamp": "2026-03-24T18:10:00Z", "active_file": "src/app.ts"}]
    )

    def fake_get_collection(request_user_id=None):
        user_key = service._collection_user_key(request_user_id)
        if service._collection_aliases.get(user_key):
            return healthy
        return broken

    monkeypatch.setattr(service, "_get_collection", fake_get_collection)

    metadatas = service.get_snapshot_metadatas(user_id=user_id, limit=2500)

    assert len(metadatas) == 1
    assert metadatas[0]["active_file"] == "src/app.ts"
    assert service._collection_aliases.get(user_id)
