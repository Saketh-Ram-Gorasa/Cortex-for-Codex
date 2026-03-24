from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any


class IncidentArchaeologyService:
    def build_investigation_plan(self, question: str, project_id: str | None, time_window: str) -> dict[str, Any]:
        normalized_question = (question or "").strip()
        normalized_project_id = (project_id or "").strip()
        normalized_time_window = (time_window or "24h").strip() or "24h"

        anchors = [token for token in normalized_question.replace("?", "").split() if len(token) >= 4][:4]
        search_queries = [normalized_question] if normalized_question else ["incident investigation"]
        if anchors:
            search_queries.append(" ".join(anchors))

        return {
            "question": normalized_question,
            "project_id": normalized_project_id or None,
            "time_window": normalized_time_window,
            "search_queries": search_queries[:2],
            "max_hypotheses": 3,
            "max_recovery_options": 3,
        }

    def build_evidence_graph(self, retrieved_items: list[dict[str, Any]]) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        contradictions: list[str] = []
        by_file: dict[str, list[dict[str, Any]]] = {}

        for index, item in enumerate(retrieved_items or []):
            node_id = str(item.get("id") or f"e_{index + 1}")
            node_file = str(item.get("active_file") or item.get("file") or "unknown")
            node_summary = str(item.get("summary") or "No summary")
            node_branch = str(item.get("git_branch") or item.get("branch") or "unknown")
            node_timestamp = str(item.get("timestamp") or datetime.now(timezone.utc).isoformat())
            node_type = str(item.get("source_type") or "snapshot")

            node = {
                "id": node_id,
                "type": node_type,
                "timestamp": node_timestamp,
                "file": node_file,
                "branch": node_branch,
                "summary": node_summary,
                "source": str(item.get("source_uri") or item.get("source_id") or "memory"),
            }
            nodes.append(node)
            by_file.setdefault(node_file, []).append(node)

        for node_file, file_nodes in by_file.items():
            branch_set = {str(row.get("branch") or "") for row in file_nodes}
            if len(branch_set) > 1:
                contradictions.append(f"Conflicting branch context for {node_file}: {', '.join(sorted(branch_set))}")

        return {
            "nodes": nodes,
            "contradictions": contradictions,
            "coverage": min(1.0, len(nodes) / 8.0),
            "recency": self._compute_recency(nodes),
        }

    def rank_hypotheses(self, evidence_graph: dict[str, Any]) -> list[dict[str, Any]]:
        nodes = list(evidence_graph.get("nodes") or [])
        if not nodes:
            return []

        keyword_counter = Counter[str]()
        for node in nodes:
            for token in str(node.get("summary") or "").lower().replace("_", " ").split():
                cleaned = token.strip(".,:;()[]{}'\"")
                if len(cleaned) >= 5:
                    keyword_counter[cleaned] += 1

        causes = [word for word, _count in keyword_counter.most_common(3)]
        if not causes:
            causes = ["environment drift"]

        max_count = max(keyword_counter.values()) if keyword_counter else 1
        hypotheses: list[dict[str, Any]] = []
        for index, cause in enumerate(causes[:3]):
            support_ids = [str(node.get("id")) for node in nodes if cause in str(node.get("summary") or "").lower()][:3]
            evidence_score = keyword_counter.get(cause, 1) / max_count
            hypotheses.append(
                {
                    "id": f"h{index + 1}",
                    "rank": index + 1,
                    "cause": cause,
                    "confidence": round(max(0.25, min(0.9, 0.45 + 0.35 * evidence_score)), 2),
                    "supportingEvidenceIds": support_ids,
                }
            )

        return hypotheses

    def compute_confidence(
        self,
        coverage: float,
        recency: float,
        contradiction_count: int,
        evidence_count: int,
    ) -> float:
        safe_coverage = max(0.0, min(float(coverage), 1.0))
        safe_recency = max(0.0, min(float(recency), 1.0))
        consistency = max(0.0, min(1.0, 1.0 - (0.18 * max(0, contradiction_count))))
        evidence_density = max(0.0, min(1.0, float(evidence_count) / 10.0))

        score = (
            0.45 * safe_coverage
            + 0.25 * safe_recency
            + 0.20 * consistency
            + 0.10 * evidence_density
        )
        contradiction_penalty = min(0.32, 0.08 * max(0, contradiction_count))
        score = max(0.05, min(0.95, score - contradiction_penalty))
        return round(score, 2)

    def simulate_recovery_options(self, hypotheses: list[dict[str, Any]], simulator_agent: Any = None) -> list[dict[str, Any]]:
        del simulator_agent

        top_cause = str((hypotheses or [{}])[0].get("cause") or "configuration fault")
        options = [
            {
                "strategy": "rollback",
                "risk": "medium",
                "blastRadius": "service",
                "estimatedTimeMinutes": 15,
                "commands": ["git checkout HEAD~1", "pytest -q"],
                "rationale": f"Revert suspected change around {top_cause}.",
            },
            {
                "strategy": "forward-fix",
                "risk": "medium",
                "blastRadius": "module",
                "estimatedTimeMinutes": 35,
                "commands": ["git checkout -b hotfix/incident", "pytest -q"],
                "rationale": f"Patch the likely fault path for {top_cause}.",
            },
            {
                "strategy": "hybrid",
                "risk": "high",
                "blastRadius": "service",
                "estimatedTimeMinutes": 45,
                "commands": ["git stash push -u", "git checkout HEAD~1", "git cherry-pick <fix-commit>"],
                "rationale": "Roll back quickly, then apply targeted fix once validated.",
            },
        ]
        return options[:3]

    def build_disproof_checks(self, hypotheses: list[dict[str, Any]]) -> list[str]:
        checks: list[str] = []
        for hypothesis in hypotheses or []:
            hypothesis_id = str(hypothesis.get("id") or "unknown")
            cause = str(hypothesis.get("cause") or "unknown cause")
            checks.append(f"Disprove {hypothesis_id}: falsify '{cause}' by reproducing failure after bypassing the suspected path.")
        return checks

    def build_contradictions(self, evidence_graph: dict[str, Any]) -> list[str]:
        return list(evidence_graph.get("contradictions") or [])

    def _compute_recency(self, nodes: list[dict[str, Any]]) -> float:
        timestamps: list[datetime] = []
        for node in nodes:
            raw = str(node.get("timestamp") or "").strip()
            if not raw:
                continue
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                timestamps.append(parsed.astimezone(timezone.utc))
            except ValueError:
                continue

        if not timestamps:
            return 0.5

        newest = max(timestamps)
        age_hours = (datetime.now(timezone.utc) - newest).total_seconds() / 3600.0
        if age_hours <= 1:
            return 1.0
        if age_hours <= 6:
            return 0.85
        if age_hours <= 24:
            return 0.7
        if age_hours <= 72:
            return 0.55
        return 0.4
