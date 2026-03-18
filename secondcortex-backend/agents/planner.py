"""
Agent 2: The Planner (The Brain)

When the user asks a question (e.g., "Why did we roll back?"), this agent:
  1. Interprets the intent of the question.
  2. Breaks it into parallel search tasks (semantic search queries).
  3. Enforces a strict max_steps=3 circuit breaker to prevent infinite loops.
  4. Hands retrieved context to the Executor agent for synthesis.
"""

from __future__ import annotations

import json
import logging
import re

from config import settings
from services.vector_db import VectorDBService
from services.llm_client import create_groq_client, get_groq_model
from services.rate_limiter import rate_limited_call

logger = logging.getLogger("secondcortex.planner")

MAX_STEPS = 1  # Reduced from 3 to conserve API quota

PLANNER_SYSTEM_PROMPT = """\
You are the SecondCortex Planner Agent. Convert a developer question into the smallest
set of high-signal semantic searches over snapshot memory.

You MUST respond with ONLY valid JSON matching this schema:
{
  "intent": "Brief description of what the developer wants to know",
  "search_queries": [
    "semantic search query 1",
    "semantic search query 2"
  ],
  "temporal_scope": "last_hour" | "last_day" | "last_week" | "all_time"
}

Rules:
- Maximum 3 search queries.
- Prefer 1-2 queries unless the question explicitly needs multiple dimensions.
- Each query must include concrete anchors from the question (file/symbol/branch/error/feature).
- If the question is vague, include one clarifying query that seeks recent evidence first.
- Avoid redundant paraphrases of the same query.
- temporal_scope must be the narrowest scope that still answers correctly.
- Return JSON only. No prose or markdown.
"""


class PlannerAgent:
    """Intercepts user questions and builds a search plan."""

    def __init__(self, vector_db: VectorDBService) -> None:
        self.vector_db = vector_db
        self.client = create_groq_client()

    async def plan(self, question: str, user_id: str | None = None) -> PlanResult:
        """
        Interpret the user's question and produce a search plan.
        Returns retrieved context chunks from Vector DB.
        """
        logger.info("Planning for question: %s", question)

        # Deterministic path for recency questions (e.g., "latest snapshot").
        # This avoids semantic retrieval returning older but semantically similar snapshots.
        if self._is_latest_lookup_question(question):
            logger.info("Detected latest-snapshot style query. Using recency retrieval.")
            timeline = await self.vector_db.get_snapshot_timeline(limit=25, user_id=user_id)
            # Timeline is oldest -> newest. For recency retrieval we want newest first.
            recent = list(reversed(timeline))
            recent = self._apply_optional_branch_filter(recent, question)
            return PlanResult(
                intent="Fetch most recent snapshot context",
                search_queries=["__recent_snapshots__"],
                temporal_scope="all_time",
                retrieved_context=recent,
            )

        # ── Step 1: Generate the search plan via LLM ────────────
        plan = await self._generate_plan(question)
        logger.info("Plan: intent=%s, queries=%s, scope=%s",
                     plan.get("intent"), plan.get("search_queries"), plan.get("temporal_scope"))

        # ── Step 2: Execute search queries (up to MAX_STEPS) ────
        search_queries = plan.get("search_queries", [question])[:MAX_STEPS]
        all_results: list[dict] = []

        for i, query in enumerate(search_queries):
            logger.info("Search step %d/%d: %s", i + 1, MAX_STEPS, query)
            results = await self.vector_db.semantic_search(query, top_k=5, user_id=user_id)
            all_results.extend(results)

        # Deduplicate by snapshot ID
        seen_ids: set[str] = set()
        unique_results: list[dict] = []
        for r in all_results:
            rid = r.get("id", "")
            if rid not in seen_ids:
                seen_ids.add(rid)
                unique_results.append(r)

        # Always seed chat context with the newest snapshot first so extension chat
        # reflects the latest captured IDE state.
        latest_timeline = await self.vector_db.get_snapshot_timeline(limit=1, user_id=user_id)
        latest_snapshot = latest_timeline[-1] if latest_timeline else None
        if latest_snapshot:
            latest_id = latest_snapshot.get("id", "")
            if latest_id and latest_id not in seen_ids:
                unique_results.insert(0, latest_snapshot)
            elif unique_results and latest_id:
                # If latest is already present, move it to the front.
                latest_idx = next((i for i, item in enumerate(unique_results) if item.get("id", "") == latest_id), -1)
                if latest_idx > 0:
                    unique_results.insert(0, unique_results.pop(latest_idx))

        return PlanResult(
            intent=plan.get("intent", question),
            search_queries=search_queries,
            temporal_scope=plan.get("temporal_scope", "all_time"),
            retrieved_context=unique_results,
        )

    def _is_latest_lookup_question(self, question: str) -> bool:
        q = (question or "").strip().lower()
        if not q:
            return False

        has_recency = bool(re.search(r"\b(latest|newest|most recent|current|last|fetch latest)\b", q))
        has_snapshot_context = bool(re.search(r"\b(snapshot|snapshots|timeline|context|update|edited|editing|file|commit|branch)\b", q))
        return has_recency and has_snapshot_context

    def _apply_optional_branch_filter(self, snapshots: list[dict], question: str) -> list[dict]:
        q = (question or "").lower()
        wants_main_branch = "main branch" in q or re.search(r"\bon\s+main\b", q)
        if wants_main_branch:
            filtered = [s for s in snapshots if str(s.get("git_branch", "")).strip().lower() == "main"]
            if filtered:
                return filtered
        return snapshots

    async def _generate_plan(self, question: str) -> dict:
        """Call GPT-4o to decompose the question into search tasks."""
        try:
            response = await rate_limited_call(
                self.client.chat.completions.create,
                model=get_groq_model(),
                messages=[
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
                temperature=0.2,
                max_tokens=400,
            )
            raw = response.choices[0].message.content or "{}"
            return json.loads(raw)
        except Exception as exc:
            logger.error("LLM Error during plan generation model=%s endpoint=%s",
                         get_groq_model(), settings.groq_endpoint, exc, exc_info=True)
            return {"intent": f"Planner Error: {str(exc)}", "search_queries": [question], "temporal_scope": "all_time"}


class PlanResult:
    """Container for the Planner's output."""

    def __init__(
        self,
        intent: str,
        search_queries: list[str],
        temporal_scope: str,
        retrieved_context: list[dict],
    ) -> None:
        self.intent = intent
        self.search_queries = search_queries
        self.temporal_scope = temporal_scope
        self.retrieved_context = retrieved_context
