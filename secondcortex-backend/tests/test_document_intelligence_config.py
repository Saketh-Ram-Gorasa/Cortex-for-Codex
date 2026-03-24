from config import Settings


def test_document_intelligence_settings_exist() -> None:
    s = Settings()
    assert hasattr(s, "azure_document_intelligence_endpoint")
    assert hasattr(s, "azure_document_intelligence_key")
    assert hasattr(s, "azure_document_intelligence_model_id")
    assert hasattr(s, "mcp_external_document_enabled")