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
import time
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
from services.llm_client import create_groq_client, get_groq_model
from services.rate_limiter import rate_limited_call

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


class RetrieverAgent:
    """Processes IDE snapshots in the background."""

    def __init__(self, vector_db: VectorDBService) -> None:
        self.vector_db = vector_db
        # Per-user previous snapshot to avoid cross-user contamination
        self._previous_snapshots: dict[str, StoredSnapshot] = {}
        # Per-user last LLM call timestamp for cooldown
        self._last_llm_call: dict[str, float] = {}

        # Initialize LLM client (Groq)
        self.client = create_groq_client()

    async def process_snapshot(self, payload: SnapshotPayload, user_id: str | None = None) -> StoredSnapshot:
        """
        Main entry point — called from BackgroundTasks.
        1. Route the snapshot (ADD/UPDATE/DELETE/NOOP).
        2. If ADD or UPDATE → extract metadata → generate embedding → store.
        """
        logger.info("Processing snapshot for %s (user=%s)", payload.active_file, user_id or "default")

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
            terminal_commands=payload.terminal_commands,
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
        elif metadata.operation == MemoryOperation.DELETE:
            logger.info("Snapshot marked as rabbit hole — not storing.")

        # Remember the latest snapshot for this user
        self._previous_snapshots[user_key] = stored
        return stored

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
            f"  Terminal commands: {payload.terminal_commands}\n"
            f"  Shadow Graph (truncated): {payload.shadow_graph[:1500]}\n"
        )

        try:
            response = await rate_limited_call(
                self.client.chat.completions.create,
                model=get_groq_model(),
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
