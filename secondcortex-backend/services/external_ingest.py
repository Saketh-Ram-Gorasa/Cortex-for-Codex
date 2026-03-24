from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ExternalMemoryRecord:
    source_type: str
    source_id: str
    source_uri: str
    domain: str
    title: str
    summary: str
    content: str
    entities: list[str]
    confidence_score: float
    timestamp: datetime
    project_id: str | None = None


class ExternalIngestionService:
    """Builds normalized external memory records and reconciles duplicates before persistence."""

    def build_slack_record(
        self,
        *,
        channel: str,
        thread_ts: str,
        messages: list[str],
        domain: str,
        project_id: str | None = None,
    ) -> ExternalMemoryRecord:
        normalized_channel = (channel or "").strip().lower()
        normalized_thread_ts = (thread_ts or "").strip()
        normalized_domain = (domain or "").strip()
        cleaned_messages = [str(message).strip() for message in (messages or []) if str(message).strip()]

        source_id = f"slack:{normalized_channel}:{normalized_thread_ts}"
        source_uri = f"slack://{normalized_channel}/{normalized_thread_ts}"
        content = "\n".join(cleaned_messages)
        entities = self._extract_entities(content)
        confidence = self._estimate_confidence(cleaned_messages, entities)

        preview = cleaned_messages[0] if cleaned_messages else "No message content"
        title = f"Slack thread in #{normalized_channel}" if normalized_channel else "Slack thread"

        return ExternalMemoryRecord(
            source_type="slack",
            source_id=source_id,
            source_uri=source_uri,
            domain=normalized_domain,
            title=title,
            summary=preview[:220],
            content=content,
            entities=entities,
            confidence_score=confidence,
            timestamp=datetime.now(timezone.utc),
            project_id=project_id,
        )

    def reconcile_records(self, records: list[ExternalMemoryRecord]) -> list[ExternalMemoryRecord]:
        deduped: dict[str, ExternalMemoryRecord] = {}
        for record in records:
            digest = hashlib.sha256(
                f"{record.source_id}|{record.title}|{record.summary}|{record.content}".encode("utf-8")
            ).hexdigest()
            existing = deduped.get(digest)
            if existing is None or record.confidence_score > existing.confidence_score:
                deduped[digest] = record
        return list(deduped.values())

    def _extract_entities(self, text: str) -> list[str]:
        if not text:
            return []
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_./-]{2,}", text)
        unique: list[str] = []
        seen = set()
        for token in tokens:
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(token)
            if len(unique) >= 20:
                break
        return unique

    def _estimate_confidence(self, messages: list[str], entities: list[str]) -> float:
        signal_count = len(messages)
        entity_count = len(entities)
        raw = 0.35 + min(signal_count, 15) * 0.02 + min(entity_count, 20) * 0.01
        return max(0.2, min(raw, 0.95))
