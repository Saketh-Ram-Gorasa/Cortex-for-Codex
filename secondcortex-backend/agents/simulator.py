"""
Agent 4: The Simulator (The Safety Agent)

Runs a "Pre-Flight" simulation for Workspace Resurrection.
Queries the local Git status and generates an impact analysis/safety report.
"""

from __future__ import annotations

import json
import logging
import subprocess
import os

from services.llm_client import create_groq_client, get_groq_model
from services.rate_limiter import rate_limited_call
from models.schemas import SafetyReport

logger = logging.getLogger("secondcortex.simulator")

SIMULATOR_SYSTEM_PROMPT = """\
You are the SecondCortex Simulator Agent (The Safety Agent).
Your task is to analyze local Git and filesystem state against a proposed Workspace Resurrection target \
to produce a Safety Report for the developer before they execute the restoration.

You MUST respond with ONLY valid JSON matching this schema:
{
  "conflicts": ["List of file paths that currently have unstashed changes which might conflict"],
  "unstashed_changes": true | false,
  "estimated_risk": "low" | "medium" | "high"
}

Rule:
- If there are uncommitted or untracked changes in the git status output, set unstashed_changes to true.
- If unstashed_changes is true, estimated_risk should be at least 'medium' (or 'high' if the target involves heavily modified files).
- Include concrete conflicting file paths when available; otherwise leave conflicts empty.
- Set estimated_risk = high when many files are modified, merge conflicts are present, or branch switch is likely destructive.
- Keep the output purely valid JSON with no markdown wrapping.
"""

class SimulatorAgent:
    """Agent that handles pre-flight checks and impact analysis."""

    def __init__(self) -> None:
        self.client = create_groq_client()

    async def analyze_impact(self, target_branch: str, workspace_dir: str | None = None) -> SafetyReport:
        """
        Query local git status and generate an impact analysis (SafetyReport).
        """
        logger.info("Simulator running impact analysis for target: %s in workspace: %s", target_branch, workspace_dir)

        # 1. Gather git status
        git_status = self._get_git_status(workspace_dir)

        # 2. Ask LLM to analyze the impact
        try:
            response = await rate_limited_call(
                self.client.chat.completions.create,
                model=get_groq_model(),
                messages=[
                    {"role": "system", "content": SIMULATOR_SYSTEM_PROMPT},
                    {
                        "role": "user", 
                        "content": f"Target Resurrection Branch/State: {target_branch}\n\nCurrent Git Status:\n{git_status}"
                    },
                ],
                temperature=0.1,
                max_tokens=300,
            )
            raw = response.choices[0].message.content or "{}"
            data = json.loads(raw)
            return SafetyReport(**data)

        except Exception as exc:
            logger.error("Simulator LLM call failed. Error: %s", exc, exc_info=True)
            # Default fallback SafetyReport
            return SafetyReport(
                conflicts=["Error determining conflicts"],
                unstashed_changes=True,
                estimated_risk="high"
            )

    def _get_git_status(self, workspace_dir: str | None) -> str:
        """Helper to run git status locally."""
        cwd = workspace_dir if workspace_dir and os.path.exists(workspace_dir) else "."
        try:
            result = subprocess.run(
                ["git", "status"],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                return result.stdout
            else:
                return f"Git status error:\n{result.stderr}"
        except Exception as exc:
            logger.warning("Failed to execute git status: %s", exc)
            return "Unable to retrieve git status. Assume there are unstashed changes."
