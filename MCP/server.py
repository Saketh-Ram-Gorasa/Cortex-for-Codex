#!/usr/bin/env python3
"""Independent MCP tools for PRD features backed by local Chroma snapshots."""

from __future__ import annotations

import json
import os
import re
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import chromadb
except Exception:  # pragma: no cover
    chromadb = None

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover
    FastMCP = None

logger = logging.getLogger(__name__)


if FastMCP is None:

    class _NoopMCP:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def tool(self, *tool_args, **tool_kwargs):
            def decorator(func):
                return func

            return decorator

        def run(self, *args, **kwargs):  # pragma: no cover
            raise RuntimeError("MCP package is not available in this environment.")

    FastMCP = _NoopMCP  # type: ignore


mcp = FastMCP("SecondCortex PRD MCP")


def _resolve_chroma_path(custom_path: str | None = None) -> str:
    if custom_path:
        candidate = Path(custom_path).expanduser()
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        return str(candidate)

    env_override = os.getenv("MCP_CHROMA_DB_PATH") or os.getenv("CHROMA_DB_PATH")
    if env_override:
        env_candidate = Path(env_override).expanduser()
        if not env_candidate.is_absolute():
            env_candidate = (Path.cwd() / env_candidate).resolve()
        return str(env_candidate)

    repo_root = Path(__file__).resolve().parent.parent
    expected = repo_root / "chroma_db"
    if expected.exists():
        return str(expected)

    return str(Path.cwd() / "chroma_db")


def _normalize_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_epoch(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        try:
            num = float(value)
        except (TypeError, ValueError):
            return 0.0
        if num > 1_000_000_000_000:
            num /= 1000.0
        return num
    text = _normalize_string(value).replace("Z", "+00:00")
    if not text:
        return 0.0
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        try:
            return float(text)
        except Exception:
            return 0.0


def _parse_entities(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip().lower() for item in raw if str(item).strip()]
    text = _normalize_string(raw)
    if not text:
        return []
    try:
        loaded = json.loads(text)
        if isinstance(loaded, (list, tuple, set)):
            return [str(item).strip().lower() for item in loaded if str(item).strip()]
    except Exception:
        pass
    return [part.strip().lower() for part in text.split(",") if part.strip()]


def _parse_commands(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = _normalize_string(raw)
    if not text:
        return []
    try:
        loaded = json.loads(text)
        if isinstance(loaded, (list, tuple, set)):
            return [str(item).strip() for item in loaded if str(item).strip()]
    except Exception:
        pass
    return [command.strip() for command in text.replace("|", ";").split(";") if command.strip()]


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9_./-]+", text.lower()) if len(token) >= 3]


def _snapshot_score(query: str, snapshot: dict[str, Any]) -> float:
    query_tokens = [token for token in _tokenize(query) if len(token) >= 3]
    if not query_tokens:
        recency = _to_epoch(snapshot.get("timestamp"))
        if recency <= 0:
            return 0.0
        now = datetime.now(timezone.utc).timestamp()
        return 1.0 / (1.0 + (now - recency) / 86_400.0)

    field_weights = {
        "summary": 3.5,
        "entities": 2.5,
        "active_file": 2.0,
        "workspace_folder": 1.0,
        "terminal_commands": 1.0,
        "shadow_graph": 0.8,
    }
    match = 0.0
    for field, weight in field_weights.items():
        text = _normalize_string(snapshot.get(field, "")).lower()
        for token in query_tokens:
            if token in text:
                match += weight
    return match


def _snapshot_confidence(snapshot: dict[str, Any]) -> float:
    candidates = [
        snapshot.get("confidence_score"),
        snapshot.get("score"),
        snapshot.get("similarity"),
    ]
    for candidate in candidates:
        try:
            raw = float(candidate)
        except Exception:
            continue
        if raw >= 0:
            return min(1.0, max(0.0, raw if raw <= 1.0 else raw / 10.0))
    return 0.6


FAILURE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "logic_error": (
        "logic",
        "off by",
        "undefined",
        "wrong",
        "bug",
        "regression",
        "misrouted",
        "null",
        "none",
        "typeerror",
        "valueerror",
        "assert",
    ),
    "performance_issue": (
        "slow",
        "timeout",
        "latency",
        "throttle",
        "performance",
        "cpu",
        "memory",
        "bottleneck",
        "lag",
    ),
    "environment_issue": (
        "permission",
        "not found",
        "missing",
        "connection",
        "env",
        "network",
        "docker",
        "host",
        "config",
        "path",
    ),
    "architectural_flaw": (
        "coupling",
        "scalability",
        "architecture",
        "design",
        "monolith",
        "circular",
        "deadlock",
        "lock",
        "data flow",
    ),
}


def _classify_failure(snapshot: dict[str, Any]) -> list[str]:
    text = _normalize_string(
        " ".join(
            [
                snapshot.get("summary", ""),
                snapshot.get("active_file", ""),
                snapshot.get("shadow_graph", ""),
                snapshot.get("workspace_folder", ""),
            ]
        )
    ).lower()
    flags = []
    for category, keywords in FAILURE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            flags.append(category)
    if flags:
        return flags
    if any(
        token in _tokenize(_normalize_string(snapshot.get("summary", "")))
        for token in ("fail", "failed", "failure", "erro", "exception")
    ):
        return ["logic_error"]
    return []


def _snapshot_is_successful(snapshot: dict[str, Any]) -> bool:
    text = _normalize_string(snapshot.get("summary", "")).lower()
    success_terms = ("fixed", "resolved", "passed", "completed", "implemented", "works", "shipped")
    return any(term in text for term in success_terms) and not _classify_failure(snapshot)


def _normalize_snapshot(raw: dict[str, Any], source: str) -> dict[str, Any]:
    payload = dict(raw or {})
    payload.setdefault("id", "")
    payload.setdefault("active_file", "")
    payload.setdefault("project_id", "")
    payload.setdefault("timestamp", "")
    payload.setdefault("summary", "")
    payload.setdefault("workspace_folder", "")
    payload.setdefault("git_branch", "")
    payload.setdefault("entities", "")
    payload["snapshot_id"] = payload.get("id") or payload.get("snapshot_id") or ""
    payload["source_collection"] = source
    payload["entities_parsed"] = _parse_entities(payload.get("entities"))
    payload["terminal_commands_parsed"] = _parse_commands(payload.get("terminal_commands"))
    return payload


@dataclass(frozen=True)
class SnapshotMatch:
    snapshot: dict[str, Any]
    score: float
    is_recent: bool


class LocalChromaSnapshotStore:
    """Direct Chroma snapshot reader used by the MCP tools."""

    def __init__(self, path: str | None = None, collection_names: list[str] | None = None) -> None:
        self.path = _resolve_chroma_path(path)
        self.collection_names = collection_names
        if chromadb is None:
            raise RuntimeError("chromadb is required for local snapshot access")
        self._client = chromadb.PersistentClient(path=self.path)

    def collection_candidates(self) -> list[str]:
        names = [name.strip() for name in (self.collection_names or []) if str(name).strip()]
        existing = [item.name for item in self._client.list_collections()]
        normalized = {name.lower() for name in existing}
        if names:
            ordered = [name for name in names if name.lower() in normalized]
            if ordered:
                return ordered

        fallback = [name for name in existing if "snapshot" in name.lower()]
        if not fallback:
            return []
        fallback.sort(reverse=True)
        return fallback

    def _iter_collections(self):
        for collection_name in self.collection_candidates():
            yield self._client.get_or_create_collection(name=collection_name), collection_name

    def search_snapshots(
        self,
        query: str,
        project_id: str | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        requested = max(1, min(int(top_k), 100))
        all_matches: list[SnapshotMatch] = []
        query_normalized = _normalize_string(query)
        dedupe: set[str] = set()

        for collection, source_name in self._iter_collections():
            try:
                total = int(collection.count() or 0)
            except Exception:
                logger.exception("Failed to read collection count for %s", source_name)
                continue
            if total <= 0:
                continue

            try:
                limit = min(total, max(requested * 5, 500))
                payload = collection.get(limit=limit, include=["metadatas"])
                metadatas = payload.get("metadatas") or []
                timestamps = payload.get("ids") or []
            except Exception:
                logger.exception("Failed fetching collection payload for %s", source_name)
                continue

            for index, raw_meta in enumerate(metadatas):
                if not raw_meta:
                    continue
                snapshot = _normalize_snapshot(dict(raw_meta), source_name)
                if project_id and _normalize_string(snapshot.get("project_id")):
                    if _normalize_string(snapshot.get("project_id")) != _normalize_string(project_id):
                        continue
                snapshot_id = _normalize_string(snapshot.get("snapshot_id"))
                if snapshot_id and snapshot_id in dedupe:
                    continue
                if snapshot_id:
                    dedupe.add(snapshot_id)
                score = _snapshot_score(query_normalized, snapshot)
                ts = _to_epoch(snapshot.get("timestamp"))
                if query_normalized and score <= 0.0:
                    continue
                if not query_normalized and ts > 0:
                    score = 1.0 / (1.0 + (datetime.now(timezone.utc).timestamp() - ts) / 86_400.0)
                all_matches.append(SnapshotMatch(snapshot=snapshot, score=score, is_recent=ts > 0))

        all_matches.sort(key=lambda item: (item.score, item.snapshot.get("timestamp", "")), reverse=True)
        if not all_matches:
            return []
        return [item.snapshot for item in all_matches[:requested]]


class _EmptySnapshotStore:
    def search_snapshots(self, query: str, project_id: str | None = None, top_k: int = 10) -> list[dict[str, Any]]:
        del query, project_id, top_k
        return []


def _format_attempts(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "snapshot_id": snapshot.get("snapshot_id", ""),
            "time": snapshot.get("timestamp", ""),
            "file": snapshot.get("active_file", ""),
            "summary": snapshot.get("summary", ""),
            "entities": snapshot.get("entities_parsed", []),
            "branch": snapshot.get("git_branch", ""),
            "terminal_commands": snapshot.get("terminal_commands_parsed", []),
            "failure_types": _classify_failure(snapshot),
            "confidence": _snapshot_confidence(snapshot),
        }
        for snapshot in snapshots
    ]


def _build_self_improving_report(
    task: str,
    latest_outcome: str,
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    outcome = _normalize_string(latest_outcome).lower()
    is_failure = any(flag in outcome for flag in ("fail", "error", "timeout"))

    attempts = _format_attempts(snapshots)
    failed_attempts = [item for item in attempts if item["failure_types"]]
    successful_attempts = [item for item in attempts if not item["failure_types"]]

    avoid_terms = Counter()
    for item in failed_attempts:
        for term in item["entities"]:
            if len(term) > 2:
                avoid_terms[term] += 1
        for command in item.get("terminal_commands", []):
            if command:
                avoid_terms[command] += 1

    use_terms = Counter()
    for item in successful_attempts:
        for command in _parse_commands(item.get("terminal_commands", [])):
            if command:
                use_terms[command] += 1

    suggestions: list[str] = []
    if is_failure and failed_attempts:
        for token, count in avoid_terms.most_common(3):
            suggestions.append(f"Avoid pattern '{token}' (seen in {count} failed snapshots).")
    if successful_attempts:
        top_success = use_terms.most_common(3)
        if top_success:
            suggestions.append(
                "Prefer validated strategies: "
                + ", ".join(f"{token} ({count}x)" for token, count in top_success)
            )
    if not suggestions:
        suggestions.append("No strong pattern found yet. Run one additional attempt and retest.")

    return {
        "feature": "self_improving_loop",
        "task": task,
        "latest_outcome": _normalize_string(latest_outcome) or "unknown",
        "attempt_count": len(attempts),
        "failed_attempts": len(failed_attempts),
        "successful_attempts": len(successful_attempts),
        "attempt_history": attempts,
        "suggested_next_strategy": suggestions,
    }


def _build_failure_memory_report(
    task: str,
    snapshots: list[dict[str, Any]],
    min_confidence: float = 0.35,
) -> dict[str, Any]:
    failures = []
    buckets: dict[str, int] = {}
    for snapshot in snapshots:
        failure_types = _classify_failure(snapshot)
        if not failure_types:
            continue
        confidence = _snapshot_confidence(snapshot)
        if confidence < min_confidence:
            continue
        failures.append(
            {
                "snapshot_id": snapshot.get("snapshot_id", ""),
                "time": snapshot.get("timestamp", ""),
                "file": snapshot.get("active_file", ""),
                "summary": snapshot.get("summary", ""),
                "failure_type": failure_types,
                "confidence": confidence,
                "task": task,
            }
        )
        for failure_type in failure_types:
            buckets[failure_type] = buckets.get(failure_type, 0) + 1

    failures.sort(key=lambda item: item["confidence"], reverse=True)

    return {
        "feature": "failure_aware_memory",
        "task": task,
        "failure_count": len(failures),
        "category_counts": buckets,
        "failures": failures,
    }


def _extract_claims(text: str) -> list[str]:
    lines = [line.strip("- •").strip() for line in text.splitlines() if line.strip()]
    statements = [line for line in lines if line]
    if statements:
        unique = []
        for statement in statements:
            normalized = _normalize_string(statement)
            if normalized and normalized not in unique:
                unique.append(normalized)
        if len(unique) > 0:
            return unique

    split = [segment.strip() for segment in re.split(r"[.!?]\s*", text) if segment.strip()]
    return split[:8]


def _evaluate_claim(snapshot: dict[str, Any], claim: str) -> str:
    claim_tokens = set(_tokenize(_normalize_string(claim)))
    snapshot_terms = set(
        _tokenize(
            " ".join(
                [
                    snapshot.get("summary", ""),
                    snapshot.get("active_file", ""),
                    snapshot.get("entities", ""),
                    snapshot.get("workspace_folder", ""),
                ]
            )
        )
    )
    overlap = len(claim_tokens & snapshot_terms)
    if overlap == 0:
        return "neutral"

    failure_types = _classify_failure(snapshot)
    negative_tokens = {"not", "avoid", "without", "missing", "never", "failed", "error"}
    if failure_types and negative_tokens.intersection(claim_tokens):
        return "contradiction"

    if overlap >= max(2, int(len(claim_tokens) * 0.25)):
        if failure_types:
            return "contradiction"
        return "support"
    return "neutral"


def _build_proof_carrying_report(
    response_text: str,
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    claims = _extract_claims(response_text)
    checks = []
    for claim in claims:
        statement = {
            "claim": claim,
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "confidence": 0.0,
            "verdict": "block",
        }
        supporting = []
        contradiction = []
        for snap in snapshots:
            decision = _evaluate_claim(snap, claim)
            entry = {
                "snapshot_id": snap.get("snapshot_id", ""),
                "summary": snap.get("summary", ""),
                "file": snap.get("active_file", ""),
                "time": snap.get("timestamp", ""),
                "failure_types": _classify_failure(snap),
                "confidence": _snapshot_confidence(snap),
            }
            if decision == "support":
                supporting.append(entry)
            elif decision == "contradiction":
                contradiction.append(entry)

        supporting.sort(key=lambda item: item["confidence"], reverse=True)
        contradiction.sort(key=lambda item: item["confidence"], reverse=True)
        statement["supporting_evidence"] = supporting[:3]
        statement["contradicting_evidence"] = contradiction[:3]
        support_score = len(statement["supporting_evidence"])
        contradiction_score = len(statement["contradicting_evidence"])

        if support_score > 0 and support_score >= contradiction_score:
            statement["verdict"] = "allow"
            statement["confidence"] = min(1.0, 0.35 + 0.2 * support_score + 0.05 * max(0, 3 - contradiction_score))
        elif support_score > 0 and contradiction_score > 0:
            statement["verdict"] = "revise"
            statement["confidence"] = 0.45
        elif contradiction_score > 0:
            statement["verdict"] = "revise"
            statement["confidence"] = 0.22
        else:
            statement["verdict"] = "block"
            statement["confidence"] = 0.0
        checks.append(statement)

    any_block = any(item["verdict"] == "block" for item in checks)
    any_revise = any(item["verdict"] == "revise" for item in checks)
    overall = "allow" if not checks else ("block" if any_block else ("revise" if any_revise else "allow"))

    return {
        "feature": "proof_carrying_response",
        "claim_count": len(checks),
        "overall_decision": overall,
        "checks": checks,
    }


_snapshot_store: Any | None = None


def _get_snapshot_store() -> Any:
    global _snapshot_store
    if _snapshot_store is None:
        try:
            _snapshot_store = LocalChromaSnapshotStore()
        except Exception:  # pragma: no cover
            logger.exception("Falling back to empty snapshot source.")
            _snapshot_store = _EmptySnapshotStore()
    return _snapshot_store


def configure_snapshot_store(store: Any | None) -> None:
    """Replace the active snapshot source for tests or alternate backends."""
    global _snapshot_store
    _snapshot_store = store


@mcp.tool()
async def self_improving_loop(
    task: str,
    latest_outcome: str = "unknown",
    project_id: str | None = None,
    top_k: int = 10,
) -> str:
    """Return structured feedback for repeated execution and learning loops."""
    store = _get_snapshot_store()
    matches = store.search_snapshots(task, project_id=project_id, top_k=top_k)
    report = _build_self_improving_report(task, latest_outcome, matches)
    return json.dumps(report, indent=2)


@mcp.tool()
async def failure_aware_memory(
    task: str,
    project_id: str | None = None,
    top_k: int = 12,
    min_confidence: float = 0.35,
) -> str:
    """Retrieve failure-memory signals by similarity and structured categories."""
    store = _get_snapshot_store()
    matches = store.search_snapshots(task, project_id=project_id, top_k=top_k)
    report = _build_failure_memory_report(task, matches, min_confidence=min_confidence)
    return json.dumps(report, indent=2)


@mcp.tool()
async def proof_carrying_response(
    proposed_response: str,
    project_id: str | None = None,
    top_k: int = 20,
) -> str:
    """Validate proposed claims against local snapshots and return evidence-backed verdicts."""
    store = _get_snapshot_store()
    matches = store.search_snapshots(proposed_response, project_id=project_id, top_k=top_k)
    report = _build_proof_carrying_report(proposed_response, matches)
    return json.dumps(report, indent=2)


if __name__ == "__main__":
    mcp.run()
