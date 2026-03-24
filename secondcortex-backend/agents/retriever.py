"""
Agent 1: The Retriever (Memory Manager & Graph Extractor)

Runs asynchronously in the background after receiving an IDE snapshot.
Uses GPT-4o (via GitHub Models or Azure OpenAI) to perform the 4-Operation Routing:
  ADD    — New task detected
  UPDATE — Continuing an existing task
  DELETE — Rabbit hole / abandoned work
  NOOP   — No meaningful change

On ADD or UPDATE, it also extracts strict JSON metadata containing
"entities" and "relations" (the Context Graph).
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime

from models.schemas import (
    MemoryMetadata,
    MemoryOperation,
    SnapshotPayload,
    StoredSnapshot,
)
from services.vector_db import VectorDBService
from services.llm_client import task_chat_completion

logger = logging.getLogger("secondcortex.retriever")

# Minimum seconds between LLM routing calls per user
RETRIEVER_COOLDOWN_SECONDS = 60

# ── System prompt for the 4-Operation Router ────────────────────

ROUTER_SYSTEM_PROMPT = """\
You are the SecondCortex Retriever Agent. Your job is to compare a new IDE \
snapshot against the previous snapshot and decide what memory operation to perform.

You MUST respond with ONLY valid JSON matching this schema:
{
  "operation": "ADD" | "UPDATE" | "DELETE" | "NOOP",
  "entities": ["entity1", "entity2"],
  "relations": [{"source": "entity1", "target": "entity2", "relation": "depends_on"}],
  "summary": "Brief description of what the developer is doing"
}

Rules:
- ADD: The developer started a genuinely new task (new file area, new feature).
- UPDATE: The developer is continuing the same task from the previous snapshot.
- DELETE: The developer abandoned the previous task (rabbit hole — switched context completely).
- NOOP: No meaningful change from the previous snapshot.
- Prefer UPDATE over ADD unless there is strong evidence of a new task boundary.
- "summary" must be one sentence, present tense, specific, and under 24 words.
- "entities" should include only high-signal identifiers (file, symbol, branch, concrete error) and avoid filler terms.
- "relations" should be sparse and factual (e.g., "edits", "calls", "fixes", "depends_on").
- Return JSON only. No markdown or commentary.
"""


NOTE_STRUCTURER_SYSTEM_PROMPT = """\
You are a strict note-structuring assistant for developer memory.

Given a raw note, return ONLY valid JSON with this exact schema:
{
    "title": "short title",
    "tags": ["tag1", "tag2"],
    "body": "normalized paragraph text",
    "summary": "one-sentence summary",
    "entities": ["EntityA", "EntityB"]
}

Rules:
- title: 3-8 words, concise, no punctuation suffix.
- tags: 1-8 lowercase snake_case tags.
- body: preserve technical meaning, remove filler, keep under 1200 chars.
- summary: under 20 words, present tense.
- entities: 0-8 high-signal terms (services, files, symbols, tools).
- Return JSON only, no markdown.
"""


class RetrieverAgent:
    """Processes IDE snapshots in the background."""

    def __init__(self, vector_db: VectorDBService) -> None:
        self.vector_db = vector_db
        # Per-user previous snapshot to avoid cross-user contamination
        self._previous_snapshots: dict[str, StoredSnapshot] = {}
        # Per-user last LLM call timestamp for cooldown
        self._last_llm_call: dict[str, float] = {}

    async def process_snapshot(self, payload: SnapshotPayload, user_id: str | None = None) -> StoredSnapshot:
        """
        Main entry point — called from BackgroundTasks.
        1. Route the snapshot (ADD/UPDATE/DELETE/NOOP).
        2. If ADD or UPDATE → extract metadata → generate embedding → store.
        """
        logger.info("Processing snapshot for %s (user=%s)", payload.active_file, user_id or "default")

        payload = await self._structure_manual_note_payload(payload)

        # ── Step 1: Route the memory operation ──────────────────
        user_key = user_id or "__anonymous__"
        previous = self._previous_snapshots.get(user_key)

        # Cooldown: skip LLM routing if last call was within RETRIEVER_COOLDOWN_SECONDS
        last_call = self._last_llm_call.get(user_key, 0)
        elapsed = time.time() - last_call

        if elapsed < RETRIEVER_COOLDOWN_SECONDS and previous is not None:
            logger.info("Cooldown active (%.0fs < %ds). Skipping LLM routing.",
                        elapsed, RETRIEVER_COOLDOWN_SECONDS)
            metadata = MemoryMetadata(
                operation=MemoryOperation.UPDATE,
                summary=f"Auto-update (cooldown): editing {payload.active_file}"
            )
        else:
            metadata = await self._route_operation(payload, previous)
            self._last_llm_call[user_key] = time.time()

        logger.info("Operation: %s | Summary: %s", metadata.operation, metadata.summary)

        # ── Step 2: Build the stored record ─────────────────────
        stored = StoredSnapshot(
            id=str(uuid.uuid4()),
            timestamp=payload.timestamp,
            workspace_folder=payload.workspace_folder,
            active_file=payload.active_file,
            language_id=payload.language_id,
            shadow_graph=payload.shadow_graph,
            git_branch=payload.git_branch,
            project_id=payload.project_id,
            terminal_commands=payload.terminal_commands,
            function_context=payload.function_context,
            metadata=metadata,
        )

        # ── Step 3: On ADD/UPDATE → embed and store in vector DB
        if metadata.operation in (MemoryOperation.ADD, MemoryOperation.UPDATE):
            logger.info("Attempting to generate embedding for snapshot %s", stored.id)
            embedding = await self.vector_db.generate_embedding(
                f"{metadata.summary}\n{payload.shadow_graph[:2000]}"
            )
            stored.embedding = embedding
            logger.info("Generated embedding length: %d. Upserting to Vector DB...", len(embedding) if embedding else 0)
            
            await self.vector_db.upsert_snapshot(stored, user_id=user_id)
            logger.info("Finished Vector DB upsert step for %s.", stored.id)
            
            # ── NEW: Extract and store facts from the snapshot ──────────────────
            await self._extract_and_store_facts(payload, metadata, stored.id, user_id)
        elif metadata.operation == MemoryOperation.DELETE:
            logger.info("Snapshot marked as rabbit hole — not storing.")

        # Remember the latest snapshot for this user
        self._previous_snapshots[user_key] = stored
        return stored

    def _is_manual_note_snapshot(self, payload: SnapshotPayload) -> bool:
        function_context = payload.function_context or {}
        return str(function_context.get("source") or "").strip().lower() == "manual_note"

    def _extract_manual_note_text(self, shadow_graph: str) -> str:
        text = (shadow_graph or "").strip()
        if not text:
            return ""
        lowered = text.lower()
        if lowered.startswith("developer note:"):
            return text.split(":", 1)[1].strip()
        return text

    def _normalize_tag(self, value: str) -> str:
        cleaned = re.sub(r"[^a-z0-9_]+", "_", (value or "").strip().lower())
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return cleaned

    def _derive_fallback_title(self, note_text: str) -> str:
        words = re.findall(r"[A-Za-z0-9_]+", note_text)
        if not words:
            return "Developer Note"
        return " ".join(words[:6]).strip().title() or "Developer Note"

    def _derive_fallback_tags(self, note_text: str, function_context: dict[str, object]) -> list[str]:
        tags: list[str] = []
        note_entities = function_context.get("noteEntities")
        if isinstance(note_entities, list):
            for item in note_entities:
                if isinstance(item, str):
                    normalized = self._normalize_tag(item)
                    if normalized:
                        tags.append(normalized)

        hashtags = re.findall(r"#([A-Za-z0-9_-]+)", note_text)
        for hashtag in hashtags:
            normalized = self._normalize_tag(hashtag)
            if normalized:
                tags.append(normalized)

        deduped: list[str] = []
        for tag in tags:
            if tag and tag not in deduped:
                deduped.append(tag)

        return deduped[:8] or ["note"]

    def _fallback_manual_note_structure(self, note_text: str, function_context: dict[str, object]) -> dict[str, object]:
        title = self._derive_fallback_title(note_text)
        tags = self._derive_fallback_tags(note_text, function_context)
        body = note_text.strip()[:1200]
        summary = body[:160].strip() or title
        entities = [tag for tag in tags if tag != "note"][:8]
        return {
            "title": title,
            "tags": tags,
            "body": body,
            "summary": summary,
            "entities": entities,
            "structuredBy": "fallback",
        }

    def _parse_json_payload(self, raw: str) -> dict[str, object]:
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
            text = re.sub(r"```$", "", text).strip()
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("Expected JSON object")
        return parsed

    async def _llm_structure_manual_note(self, note_text: str) -> dict[str, object]:
        response = await task_chat_completion(
            task="retriever",
            messages=[
                {"role": "system", "content": NOTE_STRUCTURER_SYSTEM_PROMPT},
                {"role": "user", "content": note_text},
            ],
            temperature=0.1,
            max_tokens=500,
        )
        raw = response.choices[0].message.content or "{}"
        data = self._parse_json_payload(raw)

        title = str(data.get("title") or "").strip()
        body = str(data.get("body") or "").strip()
        summary = str(data.get("summary") or "").strip()

        tags_raw = data.get("tags")
        tags: list[str] = []
        if isinstance(tags_raw, list):
            for item in tags_raw:
                if isinstance(item, str):
                    normalized = self._normalize_tag(item)
                    if normalized:
                        tags.append(normalized)
        tags = list(dict.fromkeys(tags))[:8]

        entities_raw = data.get("entities")
        entities: list[str] = []
        if isinstance(entities_raw, list):
            for item in entities_raw:
                if isinstance(item, str):
                    normalized = item.strip()
                    if normalized:
                        entities.append(normalized)
        entities = list(dict.fromkeys(entities))[:8]

        if not body:
            raise ValueError("Structured note body is empty")

        return {
            "title": title or self._derive_fallback_title(note_text),
            "tags": tags or ["note"],
            "body": body[:1200],
            "summary": summary or body[:160],
            "entities": entities,
            "structuredBy": "llm",
        }

    async def _structure_manual_note_payload(self, payload: SnapshotPayload) -> SnapshotPayload:
        if not self._is_manual_note_snapshot(payload):
            return payload

        raw_note = self._extract_manual_note_text(payload.shadow_graph)
        if not raw_note:
            return payload

        context = dict(payload.function_context or {})
        try:
            structured = await self._llm_structure_manual_note(raw_note)
        except Exception as exc:
            logger.warning("Manual note structuring failed; using fallback. error=%s", exc)
            structured = self._fallback_manual_note_structure(raw_note, context)

        title = str(structured.get("title") or "Developer Note").strip()
        tags = [str(tag).strip() for tag in (structured.get("tags") or []) if str(tag).strip()][:8]
        body = str(structured.get("body") or raw_note).strip()
        summary = str(structured.get("summary") or body[:160]).strip()
        entities = [str(entity).strip() for entity in (structured.get("entities") or []) if str(entity).strip()][:8]
        structured_by = str(structured.get("structuredBy") or "fallback").strip()

        payload.shadow_graph = (
            "Structured developer note:\n"
            f"Title: {title}\n"
            f"Tags: {', '.join(tags) if tags else 'note'}\n"
            "Body:\n"
            f"{body}"
        )

        context["noteTitle"] = title
        context["noteTags"] = tags
        context["noteBody"] = body
        context["noteSummary"] = summary
        existing_entities_raw = context.get("noteEntities")
        existing_entities = existing_entities_raw if isinstance(existing_entities_raw, list) else []
        merged_entities = [*existing_entities, *entities]
        context["noteEntities"] = list(dict.fromkeys([str(item).strip() for item in merged_entities if str(item).strip()]))[:12]
        context["noteStructuredBy"] = structured_by
        payload.function_context = context
        return payload

    async def _route_operation(self, payload: SnapshotPayload, previous: StoredSnapshot | None = None) -> MemoryMetadata:
        """Call GPT-4o to decide the memory operation."""
        previous_context = ""
        if previous:
            previous_context = (
                f"Previous snapshot:\n"
                f"  File: {previous.active_file}\n"
                f"  Branch: {previous.git_branch}\n"
                f"  Summary: {previous.metadata.summary if previous.metadata else 'N/A'}\n"
                f"  Shadow Graph (truncated): {previous.shadow_graph[:500]}\n"
            )

        user_message = (
            f"{previous_context}\n"
            f"New snapshot:\n"
            f"  File: {payload.active_file}\n"
            f"  Branch: {payload.git_branch}\n"
            f"  Language: {payload.language_id}\n"
            f"  Active symbol: {(payload.function_context or {}).get('activeSymbol', 'none')}\n"
            f"  Function signatures: {(payload.function_context or {}).get('signatures', [])[:12]}\n"
            f"  Terminal commands: {payload.terminal_commands}\n"
            f"  Shadow Graph (truncated): {payload.shadow_graph[:1500]}\n"
        )

        try:
            response = await task_chat_completion(
                task="retriever",
                messages=[
                    {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1,
                max_tokens=600,
            )

            raw = response.choices[0].message.content or "{}"
            data = json.loads(raw)
            return MemoryMetadata(**data)

        except Exception as exc:
            logger.error("Router LLM call failed: %s", exc)
            return MemoryMetadata(operation=MemoryOperation.NOOP, summary="LLM call failed")

    async def _extract_and_store_facts(
        self,
        payload,  # SnapshotPayload
        metadata,  # MemoryMetadata
        snapshot_id: str,
        user_id: str | None,
    ) -> None:
        """Extract entities/insights from snapshot and persist as facts."""
        try:
            from models.schemas import Fact
            import uuid as uuid_lib
            
            logger.info("Extracting facts from snapshot %s", snapshot_id)
            
            # Call LLM to extract structured facts
            prompt = f"""
Extract key facts from this developer snapshot in JSON format:
{{
  "facts": [
    {{"content": "...", "kind": "world|experience|opinion", "salience": 0.0-1.0, "entities": ["entity1"]}}
  ]
}}

Snapshot summary: {metadata.summary}
Active file: {payload.active_file}
Shadow graph: {payload.shadow_graph[:1000]}

Return ONLY valid JSON. Max 3 facts. Be specific and factual.
"""
            
            response = await task_chat_completion(
                task="retriever",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=400,
            )
            
            raw = response.choices[0].message.content or "{}"
            data = json.loads(raw)
            
            for fact_data in data.get("facts", []):
                fact = Fact(
                    id=str(uuid_lib.uuid4()),
                    content=fact_data.get("content", ""),
                    kind=fact_data.get("kind", "experience"),
                    salience=min(1.0, max(0.0, float(fact_data.get("salience", 0.5)))),
                    confidence=0.7,  # LLM-extracted facts start at medium confidence
                    entities=fact_data.get("entities", []),
                    source_snapshot_id=snapshot_id,
                    created_at=payload.timestamp,
                    last_accessed_at=payload.timestamp,
                )
                await self.vector_db.upsert_fact(fact, user_id=user_id)
                logger.info("Stored fact: %s", fact.id)
        
        except Exception as exc:
            logger.warning("Fact extraction failed for snapshot %s: %s", snapshot_id, exc)
            # Non-blocking; snapshot still succeeded
