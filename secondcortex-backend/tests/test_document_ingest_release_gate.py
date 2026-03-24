from pathlib import Path


def test_release_checklist_mentions_document_ingestion() -> None:
    checklist = Path("docs/hax/HAX_RELEASE_CHECKLIST.md").read_text(encoding="utf-8").lower()
    assert "document" in checklist
    assert "provenance" in checklist