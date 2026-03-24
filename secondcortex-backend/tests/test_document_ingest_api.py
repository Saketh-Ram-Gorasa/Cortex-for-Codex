from fastapi.testclient import TestClient


def test_document_ingest_api_returns_record_id(monkeypatch):
    import main as main_module

    class _FakeDocService:
        def __init__(self, endpoint: str, api_key: str, model_id: str):
            self.endpoint = endpoint
            self.api_key = api_key
            self.model_id = model_id

        def extract_text_from_bytes(self, content: bytes, mime_type: str | None = None):
            return {
                "text": "Auth fallback and retry strategy",
                "pages": 1,
                "language": "en",
                "confidence": 0.9,
                "warnings": [],
            }

    main_module.app.dependency_overrides[main_module.get_current_user] = lambda: "u1"
    monkeypatch.setattr(main_module, "AzureDocumentIntelligenceService", _FakeDocService)
    monkeypatch.setattr(main_module.settings, "mcp_external_ingestion_enabled", True)
    monkeypatch.setattr(main_module.settings, "mcp_external_document_enabled", True)
    monkeypatch.setattr(main_module.settings, "azure_document_intelligence_endpoint", "https://example.cognitiveservices.azure.com")
    monkeypatch.setattr(main_module.settings, "azure_document_intelligence_key", "key")
    monkeypatch.setattr(main_module.settings, "azure_document_intelligence_model_id", "prebuilt-read")

    async def fake_upsert(*args, **kwargs):
        return "doc-123"

    monkeypatch.setattr(main_module.vector_db, "upsert_external_record", fake_upsert)

    client = TestClient(main_module.app)
    response = client.post(
        "/api/v1/ingest/document",
        json={
            "filename": "design.pdf",
            "contentBase64": "SGVsbG8=",
            "domain": "architecture",
            "projectId": "proj_123",
        },
    )
    assert response.status_code == 200
    assert response.json().get("recordId")

    main_module.app.dependency_overrides.clear()