"""
Agent 3: The Executor (The Synthesizer)

Takes the retrieved context from the Planner and:
  1. Synthesizes a timeline / story of what happened.
  2. Runs an Internal Validation Loop — checks the draft against the original
     user prompt, flagging any discrepancies (e.g., "Slack says X, Git says Y").
  3. Formats the final output as a JSON execution array for the VS Code extension
     (Workspace Resurrection commands).
"""

from __future__ import annotations

import json
import logging

from agents.planner import PlanResult
from models.schemas import QueryResponse, ResurrectionCommand
from services.llm_client import create_llm_client, get_chat_model

logger = logging.getLogger("secondcortex.executor")

EXECUTOR_SYSTEM_PROMPT = """\
You are the SecondCortex Executor Agent. You receive retrieved context \
(snapshots from the developer's IDE history) and the original user question. \
Your job is to synthesize a clear, accurate timeline/story answering their question.

You MUST respond with ONLY valid JSON matching this schema:
{
  "summary": "A clear, human-readable answer to the question",
  "reasoning_log": [
    "Step 1: Found commit on branch fix-payment at 14:30...",
    "Step 2: Cross-referenced with file auth.go..."
  ],
  "confidence": 0.0 to 1.0,
  "discrepancies": ["Optional: any conflicting data points found"],
  "commands": [
    {
      "type": "git_stash" | "git_checkout" | "open_file" | "split_terminal" | "run_command",
      "branch": "optional",
      "filePath": "optional",
      "viewColumn": 1,
      "command": "optional"
    }
  ]
}

Rules:
- "summary" must directly answer the user's question.
- "reasoning_log" shows your chain of thought for transparency.
- "confidence" must be between 0.0 and 1.0. If below 0.85, include discrepancies.
- "commands" are optional Workspace Resurrection instructions.
"""

VALIDATION_PROMPT = """\
You are the SecondCortex Internal Validator. Compare the following draft answer \
against the original question and retrieved evidence. Check for:
1. Does the answer actually address the question?
2. Are there conflicting data points?
3. Is the confidence justified?

Respond with JSON:
{
  "is_valid": true | false,
  "issues": ["list of issues if any"],
  "revised_confidence": 0.0 to 1.0
}
"""


class ExecutorAgent:
    """Synthesizes answers and validates them internally."""

    def __init__(self) -> None:
        self.client = create_llm_client()

    async def synthesize(self, question: str, plan_result: PlanResult) -> QueryResponse:
        """
        Main entry point:
        1. Draft an answer from retrieved context.
        2. Validate internally.
        3. Return the final QueryResponse.
        """
        logger.info("Synthesizing answer for: %s", question)

        # ── Step 1: Build context string from retrieved snapshots ─
        context_parts: list[str] = []
        for i, ctx in enumerate(plan_result.retrieved_context[:10]):
            context_parts.append(
                f"[Snapshot {i + 1}]\n"
                f"  File: {ctx.get('active_file', 'N/A')}\n"
                f"  Branch: {ctx.get('git_branch', 'N/A')}\n"
                f"  Time: {ctx.get('timestamp', 'N/A')}\n"
                f"  Summary: {ctx.get('summary', 'N/A')}\n"
                f"  Code: {str(ctx.get('shadow_graph', ''))[:500]}\n"
            )
        context_block = "\n".join(context_parts) if context_parts else "No relevant context found."

        # ── Step 2: Draft the answer ─────────────────────────────
        draft = await self._generate_draft(question, context_block)

        # ── Step 3: Internal Validation Loop ─────────────────────
        validation = await self._validate_draft(question, draft, context_block)

        confidence = draft.get("confidence", 0.5)
        revised_confidence = validation.get("revised_confidence", confidence)

        # Log discrepancies visibly
        issues = validation.get("issues", [])
        discrepancies = draft.get("discrepancies", [])
        if issues:
            logger.warning("VALIDATION ISSUES: %s", issues)
            discrepancies.extend(issues)

        if revised_confidence < 0.85:
            logger.warning(
                "Low confidence (%.2f) — discrepancies: %s",
                revised_confidence, discrepancies
            )

        # ── Step 4: Build the response ───────────────────────────
        reasoning_log = draft.get("reasoning_log", [])
        if discrepancies:
            reasoning_log.append(f"⚠️ Discrepancies flagged: {discrepancies}")

        commands = [
            ResurrectionCommand(**cmd)
            for cmd in draft.get("commands", [])
        ]

        return QueryResponse(
            summary=draft.get("summary", "I could not determine a clear answer."),
            reasoning_log=reasoning_log,
            commands=commands,
        )

    async def _generate_draft(self, question: str, context: str) -> dict:
        """Call LLM to draft the answer."""
        try:
            response = self.client.chat.completions.create(
                model=get_chat_model(),
                messages=[
                    {"role": "system", "content": EXECUTOR_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Question: {question}\n\nRetrieved Context:\n{context}"},
                ],
                temperature=0.3,
                max_tokens=1200,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            return json.loads(raw)
        except Exception as exc:
            logger.error("Executor LLM call failed: %s", exc)
            return {"summary": "Error generating answer.", "confidence": 0.0}

    async def _validate_draft(self, question: str, draft: dict, context: str) -> dict:
        """Internal Validation Loop — checks draft against the evidence."""
        try:
            response = self.client.chat.completions.create(
                model=get_chat_model(),
                messages=[
                    {"role": "system", "content": VALIDATION_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Original Question: {question}\n\n"
                            f"Draft Answer: {json.dumps(draft)}\n\n"
                            f"Evidence:\n{context}"
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            return json.loads(raw)
        except Exception as exc:
            logger.error("Validation LLM call failed: %s", exc)
            return {"is_valid": True, "issues": [], "revised_confidence": 0.5}
