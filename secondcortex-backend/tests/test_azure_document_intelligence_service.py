from services.azure_document_intelligence import AzureDocumentIntelligenceService


def test_extract_text_requires_config() -> None:
    svc = AzureDocumentIntelligenceService(endpoint="", api_key="", model_id="prebuilt-read")
    ok, result = svc.validate_configuration()
    assert ok is False
    assert "endpoint" in result.lower() or "key" in result.lower()


def test_extract_text_rejects_empty_content() -> None:
    svc = AzureDocumentIntelligenceService(endpoint="https://example.cognitiveservices.azure.com", api_key="x", model_id="prebuilt-read")
    result = svc.extract_text_from_bytes(b"")
    assert "error" in result
    assert "content" in result["error"].lower()