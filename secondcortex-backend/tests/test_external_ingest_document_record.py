from services.external_ingest import ExternalIngestionService


def test_build_document_record_generates_provenance() -> None:
    svc = ExternalIngestionService()
    record = svc.build_document_record(
        source_name="Design Doc",
        source_uri="https://contoso.sharepoint.com/docs/design.pdf",
        domain="architecture",
        extracted_text="Auth fallback and retry strategy. The design includes queue backpressure handling.",
        project_id="proj_123",
    )
    assert record.source_type == "document"
    assert record.source_uri.startswith("https://")
    assert record.project_id == "proj_123"
    assert len(record.entities) > 0