from __future__ import annotations

from typing import Any


class AzureDocumentIntelligenceService:
    """Thin wrapper around Azure AI Document Intelligence OCR extraction."""

    def __init__(self, endpoint: str, api_key: str, model_id: str = "prebuilt-read") -> None:
        self.endpoint = (endpoint or "").strip()
        self.api_key = (api_key or "").strip()
        self.model_id = (model_id or "prebuilt-read").strip() or "prebuilt-read"

    def validate_configuration(self) -> tuple[bool, str]:
        missing: list[str] = []
        if not self.endpoint:
            missing.append("endpoint")
        if not self.api_key:
            missing.append("key")

        if missing:
            return False, f"Missing Document Intelligence configuration: {', '.join(missing)}"
        return True, "ok"

    def extract_text_from_bytes(self, content: bytes, mime_type: str | None = None) -> dict[str, Any]:
        ok, message = self.validate_configuration()
        if not ok:
            return {"error": message, "text": "", "pages": 0, "language": "", "confidence": 0.0, "warnings": []}

        if not content:
            return {
                "error": "Document content must be non-empty bytes.",
                "text": "",
                "pages": 0,
                "language": "",
                "confidence": 0.0,
                "warnings": [],
            }

        try:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
            from azure.core.credentials import AzureKeyCredential
        except Exception as exc:
            return {
                "error": f"Azure Document Intelligence SDK is not available: {exc}",
                "text": "",
                "pages": 0,
                "language": "",
                "confidence": 0.0,
                "warnings": [],
            }

        try:
            client = DocumentIntelligenceClient(
                endpoint=self.endpoint,
                credential=AzureKeyCredential(self.api_key),
            )

            content_type = (mime_type or "application/octet-stream").strip() or "application/octet-stream"
            poller = client.begin_analyze_document(
                model_id=self.model_id,
                body=AnalyzeDocumentRequest(bytes_source=content),
                content_type=content_type,
            )
            result = poller.result()

            lines: list[str] = []
            languages: list[str] = []
            confidences: list[float] = []
            page_count = 0

            for page in (result.pages or []):
                page_count += 1
                for line in (page.lines or []):
                    line_text = (line.content or "").strip()
                    if line_text:
                        lines.append(line_text)

            for language in (result.languages or []):
                locale = (getattr(language, "locale", "") or "").strip()
                if locale:
                    languages.append(locale)
                confidence = getattr(language, "confidence", None)
                if isinstance(confidence, (int, float)):
                    confidences.append(float(confidence))

            language = languages[0] if languages else ""
            confidence = sum(confidences) / len(confidences) if confidences else 0.7

            return {
                "text": "\n".join(lines).strip(),
                "pages": int(page_count or 0),
                "language": language,
                "confidence": max(0.0, min(confidence, 1.0)),
                "warnings": [],
            }
        except Exception as exc:
            return {
                "error": f"Document extraction failed: {exc}",
                "text": "",
                "pages": 0,
                "language": "",
                "confidence": 0.0,
                "warnings": [],
            }