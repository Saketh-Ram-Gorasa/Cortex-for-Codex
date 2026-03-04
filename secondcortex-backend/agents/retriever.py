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
import uuid
from datetime import datetime

from config import settings
from models.schemas import (
    MemoryMetadata,
    MemoryOperation,
    SnapshotPayload,
    StoredSnapshot,
)
from services.vector_db import VectorDBService
from services.llm_client import create_llm_client, get_chat_model

logger = logging.getLogger("secondcortex.retriever")

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
- "entities" should be identifiers like file names, function names, branch names, error messages.
- "relations" should describe how entities relate (e.g., "calls", "depends_on", "fixes").
"""


class RetrieverAgent:
    """Processes IDE snapshots in the background."""

    def __init__(self, vector_db: VectorDBService) -> None:
        self.vector_db = vector_db
        self._previous_snapshot: StoredSnapshot | None = None

        # Initialize LLM client (GitHub Models or Azure OpenAI)
        self.client = create_llm_client()

    async def process_snapshot(self, payload: SnapshotPayload, user_id: str | None = None) -> StoredSnapshot:
        """
        Main entry point — called from BackgroundTasks.
        1. Route the snapshot (ADD/UPDATE/DELETE/NOOP).
        2. If ADD or UPDATE → extract metadata → generate embedding → store.
        """
        logger.info("Processing snapshot for %s (user=%s)", payload.active_file, user_id or "default")

        # ── Step 1: Route the memory operation ──────────────────
        metadata = await self._route_operation(payload)
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
            terminal_commands=payload.terminal_commands,
            metadata=metadata,
        )

        # ── Step 3: On ADD/UPDATE → embed and store in vector DB
        if metadata.operation in (MemoryOperation.ADD, MemoryOperation.UPDATE):
            embedding = await self.vector_db.generate_embedding(
                f"{metadata.summary}\n{payload.shadow_graph[:2000]}"
            )
            stored.embedding = embedding
            await self.vector_db.upsert_snapshot(stored, user_id=user_id)
            logger.info("Stored snapshot %s in Vector DB.", stored.id)
        elif metadata.operation == MemoryOperation.DELETE:
            logger.info("Snapshot marked as rabbit hole — not storing.")

        # Remember the latest snapshot for comparison
        self._previous_snapshot = stored
        return stored

    async def _route_operation(self, payload: SnapshotPayload) -> MemoryMetadata:
        """Call GPT-4o to decide the memory operation."""
        previous_context = ""
        if self._previous_snapshot:
            previous_context = (
                f"Previous snapshot:\n"
                f"  File: {self._previous_snapshot.active_file}\n"
                f"  Branch: {self._previous_snapshot.git_branch}\n"
                f"  Summary: {self._previous_snapshot.metadata.summary if self._previous_snapshot.metadata else 'N/A'}\n"
                f"  Shadow Graph (truncated): {self._previous_snapshot.shadow_graph[:500]}\n"
            )

        user_message = (
            f"{previous_context}\n"
            f"New snapshot:\n"
            f"  File: {payload.active_file}\n"
            f"  Branch: {payload.git_branch}\n"
            f"  Language: {payload.language_id}\n"
            f"  Terminal commands: {payload.terminal_commands}\n"
            f"  Shadow Graph (truncated): {payload.shadow_graph[:1500]}\n"
        )

        try:
            response = self.client.chat.completions.create(
                model=get_chat_model(),
                messages=[
                    {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1,
                max_tokens=600,
                response_format={"type": "json_object"},
            )

            raw = response.choices[0].message.content or "{}"
            data = json.loads(raw)
            return MemoryMetadata(**data)

        except Exception as exc:
            logger.error("Router LLM call failed: %s", exc)
            return MemoryMetadata(operation=MemoryOperation.NOOP, summary="LLM call failed")
