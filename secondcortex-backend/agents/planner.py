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

from config import settings
from services.vector_db import VectorDBService
from services.llm_client import create_groq_client, get_groq_model
from services.rate_limiter import rate_limited_call

logger = logging.getLogger("secondcortex.planner")

MAX_STEPS = 1  # Reduced from 3 to conserve API quota

PLANNER_SYSTEM_PROMPT = """\
Break a developer question into 1-2 high-signal semantic searches for IDE snapshots.

Respond with ONLY valid JSON (no prose, no markdown):
{
  "intent": "Brief intent",
  "search_queries": ["query1"],
  "temporal_scope": "last_hour" | "last_day" | "all_time"
}

Rules:
- Max 2 queries (prefer 1).
- Include concrete anchors from question (file/error/branch/symbol).
- If vague, add 1 clarifying query for recent evidence.
- temporal_scope: Narrowest scope that answers the question.
- Return JSON only.
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

        return PlanResult(
            intent=plan.get("intent", question),
            search_queries=search_queries,
            temporal_scope=plan.get("temporal_scope", "all_time"),
            retrieved_context=unique_results,
        )

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
