#!/usr/bin/env python3
"""
SecondCortex MCP Server

Exposes the SecondCortex "Cortex Memory" (ChromaDB semantic search) as a tool
via the Model Context Protocol (MCP), so it can be queried by AI assistants like Claude Desktop or Cursor.
"""

import sys
import os
import base64
import logging
import time
import functools
from collections import deque
from collections import Counter
from collections import defaultdict
from datetime import datetime, timezone

# Ensure the backend directory is in the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from config import settings
from services.vector_db import VectorDBService
from services.external_ingest import ExternalIngestionService
from services.azure_document_intelligence import AzureDocumentIntelligenceService
from services.incident_archaeology import IncidentArchaeologyService
from auth.database import UserDB

# Initialize logging for MCP server
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("secondcortex.mcp")

# Initialize the VectorDB service
logger.info("Initializing VectorDBService for MCP...")
vector_db = VectorDBService()
user_db = UserDB()
external_ingest = ExternalIngestionService()
incident_archaeology = IncidentArchaeologyService()

# Create the MCP Server, allowing ANY Production Host (Public)
mcp = FastMCP(
    "SecondCortex API",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(settings.mcp_dns_rebinding_protection_enabled)
    )
)


class _KeyRateLimiter:
    def __init__(self, calls_per_minute: int) -> None:
        self.calls_per_minute = max(1, int(calls_per_minute))
        self._calls: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        window_start = now - 60.0
        bucket = self._calls.setdefault(key, deque())
        while bucket and bucket[0] < window_start:
            bucket.popleft()
        if len(bucket) >= self.calls_per_minute:
            return False
        bucket.append(now)
        return True


_rate_limiter = _KeyRateLimiter(settings.mcp_rate_limit_per_minute)
_task_summary_cache: dict[tuple[str, str, str, str], dict] = {}
_METRIC_SAMPLE_SIZE = 500
_mcp_metrics = {
    "started_at": time.time(),
    "requests_total": 0,
    "success_total": 0,
    "error_total": 0,
    "auth_failures": 0,
    "rate_limited": 0,
    "oversized_rejections": 0,
    "task_cache_hit": 0,
    "task_cache_miss": 0,
    "task_cache_stale_rebuilt": 0,
    "tool_counts": Counter(),
    "tool_latency_ms": defaultdict(lambda: deque(maxlen=_METRIC_SAMPLE_SIZE)),
    "graph_discovered_nodes": deque(maxlen=_METRIC_SAMPLE_SIZE),
}


def _record_latency(tool_name: str, latency_ms: float) -> None:
    _mcp_metrics["tool_latency_ms"][tool_name].append(max(0.0, float(latency_ms)))


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return float(ordered[idx])


def _track_mcp_tool(tool_name: str):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            _mcp_metrics["requests_total"] += 1
            _mcp_metrics["tool_counts"][tool_name] += 1
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                _mcp_metrics["success_total"] += 1
                return result
            except Exception:
                _mcp_metrics["error_total"] += 1
                raise
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                _record_latency(tool_name, elapsed_ms)

        return wrapper

    return decorator


def _resolve_api_key(api_key: str | None) -> str | None:
    raw = (api_key or "").strip()
    if raw:
        return raw

    # Claude Desktop / Cursor / Copilot local bridge compatibility:
    # allow injecting key via env instead of pasting it in every chat.
    fallback = os.getenv("SECONDCORTEX_MCP_API_KEY", "").strip()
    return fallback or None


def _normalize_top_k(top_k: int | None) -> int:
    requested_top_k = int(top_k if top_k is not None else settings.mcp_default_top_k)
    return max(1, min(requested_top_k, int(settings.mcp_max_top_k)))


def _parse_entities(raw_entities: str | list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    if raw_entities is None:
        return []

    if isinstance(raw_entities, (list, tuple, set)):
        return [str(entity).strip() for entity in raw_entities if str(entity).strip()]

    raw = str(raw_entities).strip()
    if not raw:
        return []
    return [entity.strip() for entity in raw.split(",") if entity.strip()]


def _format_snapshot_block(meta: dict, *, include_code_chars: int = 400) -> str:
    timestamp = meta.get("timestamp", "Unknown Time")
    file_path = meta.get("active_file", "Unknown File")
    branch = meta.get("git_branch", "Unknown Branch")
    summary = meta.get("summary", "No summary")
    entities = _parse_entities(meta.get("entities"))
    active_symbol = str(meta.get("active_symbol") or "").strip()
    source_type = str(meta.get("source_type") or "").strip()
    source_id = str(meta.get("source_id") or "").strip()
    source_uri = str(meta.get("source_uri") or "").strip()
    confidence = meta.get("confidence_score")

    block = (
        f"Time: {timestamp}\n"
        f"File: {file_path}\n"
        f"Branch: {branch}\n"
        f"Summary: {summary}\n"
    )
    if active_symbol:
        block += f"Active Symbol: {active_symbol}\n"
    if entities:
        block += f"Entities: {', '.join(entities[:8])}\n"
    if source_type:
        block += f"Source: {source_type} ({source_id or 'unknown'})\n"
    if source_uri:
        block += f"Source URI: {source_uri}\n"
    if confidence not in (None, ""):
        block += f"Confidence: {confidence}\n"

    code_context = str(meta.get("shadow_graph") or "")
    if code_context and include_code_chars > 0:
        snippet = code_context[:include_code_chars] + ("..." if len(code_context) > include_code_chars else "")
        block += f"Code Context:\n```\n{snippet}\n```\n"
    return block


def _approx_chars_for_tokens(max_tokens: int) -> int:
    safe_tokens = max(100, min(int(max_tokens), 4000))
    return safe_tokens * 4


def _pick_entity_anchor(anchor: str) -> str:
    return (anchor or "").strip().lower()


def _extract_terms_for_debug(meta: dict) -> set[str]:
    terms: set[str] = set()
    for entity in _parse_entities(meta.get("entities")):
        terms.add(entity.strip().lower())
    for token in str(meta.get("summary") or "").lower().replace("_", " ").split():
        token = token.strip(".,:;()[]{}'\"`")
        if len(token) >= 4:
            terms.add(token)
    active_symbol = str(meta.get("active_symbol") or "").strip().lower()
    if active_symbol:
        terms.add(active_symbol)
    return terms


def _classify_relationship(
    anchor: str,
    candidate: str,
    snapshots: list[dict],
    *,
    preferred: set[str],
) -> tuple[str, int]:
    co_changed = 0
    co_debugged = 0
    causally_linked = 0

    latest_anchor_ts = 0.0
    earliest_candidate_ts = float("inf")

    for meta in snapshots:
        entities = {e.strip().lower() for e in _parse_entities(meta.get("entities"))}
        if anchor in entities and candidate in entities:
            co_changed += 1

        debug_terms = _extract_terms_for_debug(meta)
        if anchor in debug_terms and candidate in debug_terms:
            co_debugged += 1

        ts = meta.get("timestamp")
        try:
            ts_val = float(ts)
        except Exception:
            try:
                from datetime import datetime

                ts_val = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
            except Exception:
                ts_val = 0.0

        if anchor in entities:
            latest_anchor_ts = max(latest_anchor_ts, ts_val)
        if candidate in entities:
            earliest_candidate_ts = min(earliest_candidate_ts, ts_val)

    if latest_anchor_ts > 0 and earliest_candidate_ts != float("inf") and latest_anchor_ts <= earliest_candidate_ts:
        causally_linked = 1

    weights = {
        "co-changed": co_changed,
        "co-debugged": co_debugged,
        "causally-linked": causally_linked,
    }
    allowed = {k: v for k, v in weights.items() if (not preferred or k in preferred)}
    if not allowed:
        return "co-changed", 0

    rel, score = max(allowed.items(), key=lambda item: item[1])
    return rel, int(score)


def _authenticate_request(
    *,
    api_key: str | None,
    query: str | None = None,
    top_k: int | None = None,
) -> tuple[dict | None, str | None, int, str]:
    normalized_query = (query or "").strip()
    if query is not None and not normalized_query:
        return None, None, 0, "Invalid request: query must be non-empty."

    if query is not None and len(normalized_query) > int(settings.mcp_max_query_chars):
        _mcp_metrics["oversized_rejections"] += 1
        return None, None, 0, f"Invalid request: query exceeds max length of {int(settings.mcp_max_query_chars)} characters."

    resolved_api_key = _resolve_api_key(api_key)
    if not resolved_api_key:
        _mcp_metrics["auth_failures"] += 1
        return None, None, 0, "Authentication required: provide api_key or set SECONDCORTEX_MCP_API_KEY for MCP client integration."

    if api_key and not bool(settings.mcp_legacy_tool_api_key_enabled):
        return None, None, 0, "Legacy api_key tool argument is disabled. Configure MCP connection auth or SECONDCORTEX_MCP_API_KEY."

    if not _rate_limiter.allow(resolved_api_key):
        _mcp_metrics["rate_limited"] += 1
        return None, None, 0, "Rate limit exceeded for MCP key. Please retry in about a minute."

    user = user_db.get_user_by_mcp_api_key(resolved_api_key)
    if not user:
        _mcp_metrics["auth_failures"] += 1
        return None, None, 0, "Authentication Failed: Invalid API Key. Please generate a valid key from your SecondCortex dashboard."

    safe_top_k = _normalize_top_k(top_k)
    return user, normalized_query, safe_top_k, ""


_TASK_TYPES = {
    "debugging",
    "code-review",
    "feature-addition",
    "incident-response",
}


def _to_unix_seconds(value: object) -> float:
    if isinstance(value, (int, float)):
        num = float(value)
        if num > 1_000_000_000_000:
            num = num / 1000.0
        return num if num > 0 else 0.0

    raw = str(value or "").strip()
    if not raw:
        return 0.0

    try:
        num = float(raw)
        if num > 1_000_000_000_000:
            num = num / 1000.0
        return num if num > 0 else 0.0
    except Exception:
        pass

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except Exception:
        return 0.0


def _build_snapshot_fingerprint(snapshots: list[dict]) -> str:
    if not snapshots:
        return "empty"

    newest_ts = 0.0
    stable_parts: list[str] = []
    for item in snapshots:
        ts = _to_unix_seconds(item.get("timestamp"))
        newest_ts = max(newest_ts, ts)
        stable_parts.append(
            "|".join(
                [
                    str(item.get("active_file") or ""),
                    str(item.get("active_symbol") or ""),
                    str(item.get("git_branch") or ""),
                ]
            )
        )

    return f"n={len(snapshots)};ts={int(newest_ts)};sig={';'.join(sorted(stable_parts)[:6])}"


def _trim_to_budget(text: str, max_tokens: int) -> str:
    budget_chars = _approx_chars_for_tokens(max_tokens)
    if len(text) <= budget_chars:
        return text
    marker = "\n[Truncated to fit token budget]"
    allowed = max(0, budget_chars - len(marker))
    return text[:allowed] + marker


def _summarize_task_context(domain: str, task_type: str, snapshots: list[dict]) -> str:
    if not snapshots:
        return f"No context found for domain '{domain}' and task '{task_type}'."

    summaries = [str(row.get("summary") or "").strip() for row in snapshots if str(row.get("summary") or "").strip()]
    files = [str(row.get("active_file") or "unknown") for row in snapshots]
    branches = [str(row.get("git_branch") or "unknown") for row in snapshots]
    entities = []
    for row in snapshots:
        entities.extend(_parse_entities(row.get("entities")))

    top_files = ", ".join([name for name, _count in Counter(files).most_common(4)]) or "none"
    top_branches = ", ".join([name for name, _count in Counter(branches).most_common(3)]) or "none"
    top_entities = ", ".join([name for name, _count in Counter(entities).most_common(6)]) or "none"
    key_points = " | ".join(summaries[:4]) if summaries else "No explicit summaries available"

    if task_type == "debugging":
        return (
            f"Task context ({task_type}) for domain '{domain}':\n"
            f"- Likely hotspots: {top_files}\n"
            f"- Candidate causes/signals: {top_entities}\n"
            f"- Recent debugging-relevant decisions: {key_points}\n"
            f"- Active branches for fixes: {top_branches}"
        )

    if task_type == "code-review":
        return (
            f"Task context ({task_type}) for domain '{domain}':\n"
            f"- Primary files to inspect: {top_files}\n"
            f"- Risky symbols/entities: {top_entities}\n"
            f"- Review themes from history: {key_points}\n"
            f"- Branch focus: {top_branches}"
        )

    if task_type == "feature-addition":
        return (
            f"Task context ({task_type}) for domain '{domain}':\n"
            f"- Existing implementation surface: {top_files}\n"
            f"- Reusable symbols/entities: {top_entities}\n"
            f"- Prior design/implementation decisions: {key_points}\n"
            f"- Active branches: {top_branches}"
        )

    return (
        f"Task context ({task_type}) for domain '{domain}':\n"
        f"- Operationally relevant files: {top_files}\n"
        f"- Incident signals/entities: {top_entities}\n"
        f"- Recent mitigation/response notes: {key_points}\n"
        f"- Active branches: {top_branches}"
    )

@mcp.tool()
@_track_mcp_tool("search_memory")
async def search_memory(query: str, api_key: str | None = None, top_k: int | None = None) -> str:
    """
    Search the developer's SecondCortex memory (long-term facts + short-term snapshots) for relevant technical context.
    
    Args:
        query: The semantic search query (e.g., "authentication logic", "database schema changes")
        api_key: Optional explicit MCP API key (legacy flow). If omitted, SECONDCORTEX_MCP_API_KEY env var is used.
        top_k: Number of relevant results to retrieve per source (default: 5)
    
    Returns:
        A formatted summary string containing both facts (long-term memory) and snapshots (short-term memory).
    """
    user, normalized_query, safe_top_k, error = _authenticate_request(api_key=api_key, query=query, top_k=top_k)
    if error:
        return error

    logger.info("MCP search_memory called query_len=%d top_k=%d", len(normalized_query), safe_top_k)

    user_id = user["id"]
    logger.info(f"MCP Authenticated for user: {user.get('display_name', user_id)}")
    
    # Dual retrieval: facts (long-term) + snapshots (short-term)
    facts = await vector_db.recall_facts(normalized_query, top_k=safe_top_k, user_id=user_id, min_salience=0.3)
    snapshots = await vector_db.semantic_search(normalized_query, top_k=safe_top_k, user_id=user_id)
    
    output_parts = []
    
    # Format facts section (long-term memory)
    if facts:
        output_parts.append(f"=== FACTS (LONG-TERM MEMORY) ===\nFound {len(facts)} relevant facts for '{normalized_query}':\n")
        for i, fact in enumerate(facts):
            kind = fact.get("kind", "unknown")
            content = fact.get("document", "No content")
            salience = fact.get("salience", 0.5)
            confidence = fact.get("confidence", 0.7)
            entities = fact.get("entities", [])
            source_snapshot = fact.get("source_snapshot_id", "Unknown")
            
            chunk = (
                f"--- Fact {i+1} ({kind}) ---\n"
                f"Content: {content}\n"
                f"Salience: {salience:.1%} | Confidence: {confidence:.1%}\n"
                f"Entities: {', '.join(entities) if entities else 'None'}\n"
                f"Source: Snapshot {source_snapshot[:8] if source_snapshot else 'Unknown'}\n"
            )
            output_parts.append(chunk)
    else:
        output_parts.append(f"No relevant facts found for '{normalized_query}'.\n")
    
    output_parts.append("\n=== SNAPSHOTS (SHORT-TERM MEMORY) ===\n")
    
    # Format snapshots section (short-term memory)
    if snapshots:
        output_parts.append(f"Found {len(snapshots)} relevant snapshots for '{normalized_query}':\n")
        for i, meta in enumerate(snapshots):
            timestamp = meta.get("timestamp", "Unknown Time")
            file_path = meta.get("active_file", "Unknown File")
            branch = meta.get("git_branch", "Unknown Branch")
            summary = meta.get("summary", "No summary")
            
            chunk = (
                f"--- Snapshot {i+1} ---\n"
                f"Time: {timestamp}\n"
                f"File: {file_path}\n"
                f"Branch: {branch}\n"
                f"Summary: {summary}\n"
                f"Entities: {meta.get('entities', 'None')}\n"
            )
            source_type = str(meta.get("source_type") or "").strip()
            source_uri = str(meta.get("source_uri") or "").strip()
            confidence = meta.get("confidence_score")
            if source_type:
                chunk += f"Source: {source_type}\n"
            if source_uri:
                chunk += f"Source URI: {source_uri}\n"
            if confidence not in (None, ""):
                chunk += f"Confidence: {confidence}\n"
            
            # Include shadow graph (code context) if available
            code_context = meta.get("shadow_graph")
            if code_context:
                code_snippet = code_context[:1000] + ("..." if len(code_context) > 1000 else "")
                chunk += f"Code Context:\n```\n{code_snippet}\n```\n"
                
            output_parts.append(chunk)
    else:
        output_parts.append(f"No relevant snapshots found for '{normalized_query}'.\n")
            
    return "\n".join(output_parts)


@mcp.tool()
@_track_mcp_tool("ingest_slack_thread")
async def ingest_slack_thread(
    channel: str,
    thread_ts: str,
    messages: list[str],
    domain: str,
    api_key: str | None = None,
    project_id: str | None = None,
) -> str:
    """Ingest a Slack thread into SecondCortex memory with provenance metadata (feature-flagged)."""
    if not bool(settings.mcp_external_ingestion_enabled):
        return "External ingestion is disabled by server policy."
    if not bool(settings.mcp_external_slack_enabled):
        return "Slack ingestion is disabled by server policy."

    if not (channel or "").strip() or not (thread_ts or "").strip() or not (domain or "").strip():
        return "Invalid request: channel, thread_ts, and domain are required."

    cleaned_messages = [str(message).strip() for message in (messages or []) if str(message).strip()]
    if not cleaned_messages:
        return "Invalid request: messages must include at least one non-empty message."

    max_messages = max(1, int(settings.mcp_external_max_messages))
    if len(cleaned_messages) > max_messages:
        cleaned_messages = cleaned_messages[:max_messages]

    auth_query = f"slack {channel} {domain}"
    user, _normalized_query, _safe_top_k, error = _authenticate_request(api_key=api_key, query=auth_query, top_k=3)
    if error:
        return error

    record = external_ingest.build_slack_record(
        channel=channel,
        thread_ts=thread_ts,
        messages=cleaned_messages,
        domain=domain,
        project_id=project_id,
    )
    reconciled = external_ingest.reconcile_records([record])
    if not reconciled:
        return "No ingestible Slack records found after reconciliation."

    saved_id = await vector_db.upsert_external_record(reconciled[0], user_id=user["id"])
    if not saved_id:
        return "Failed to persist Slack thread into memory."

    return (
        f"Slack thread ingested successfully.\n"
        f"- Record ID: {saved_id}\n"
        f"- Source: {reconciled[0].source_uri}\n"
        f"- Domain: {reconciled[0].domain}\n"
        f"- Confidence: {reconciled[0].confidence_score:.2f}\n"
        f"- Entities extracted: {', '.join(reconciled[0].entities[:8]) or 'none'}"
    )


@mcp.tool()
@_track_mcp_tool("ingest_document")
async def ingest_document(
    filename: str,
    content_base64: str,
    domain: str,
    source_uri: str | None = None,
    api_key: str | None = None,
    project_id: str | None = None,
) -> str:
    """Ingest a document using Azure AI Document Intelligence OCR/extraction (feature-flagged)."""
    if not bool(settings.mcp_external_ingestion_enabled):
        return "External ingestion is disabled by server policy."
    if not bool(settings.mcp_external_document_enabled):
        return "Document ingestion is disabled by server policy."

    normalized_filename = (filename or "").strip()
    normalized_domain = (domain or "").strip()
    normalized_payload = (content_base64 or "").strip()
    normalized_source_uri = (source_uri or "").strip()

    if not normalized_filename or not normalized_domain or not normalized_payload:
        return "Invalid request: filename, content_base64, and domain are required."

    auth_query = f"document {normalized_filename} {normalized_domain}"
    user, _normalized_query, _safe_top_k, error = _authenticate_request(api_key=api_key, query=auth_query, top_k=3)
    if error:
        return error

    try:
        content_bytes = base64.b64decode(normalized_payload, validate=True)
    except Exception:
        return "Invalid request: content_base64 must be valid base64-encoded bytes."

    content_type = "application/octet-stream"
    lowered = normalized_filename.lower()
    if lowered.endswith(".pdf"):
        content_type = "application/pdf"
    elif lowered.endswith(".png"):
        content_type = "image/png"
    elif lowered.endswith(".jpg") or lowered.endswith(".jpeg"):
        content_type = "image/jpeg"

    extractor = AzureDocumentIntelligenceService(
        endpoint=settings.azure_document_intelligence_endpoint,
        api_key=settings.azure_document_intelligence_key,
        model_id=settings.azure_document_intelligence_model_id,
    )

    extraction = extractor.extract_text_from_bytes(content_bytes, mime_type=content_type)
    if extraction.get("error"):
        return f"Document extraction failed: {extraction.get('error')}"

    extracted_text = str(extraction.get("text") or "").strip()
    if not extracted_text:
        return "Document extraction returned empty text; nothing to ingest."

    record = external_ingest.build_document_record(
        source_name=normalized_filename,
        source_uri=normalized_source_uri,
        domain=normalized_domain,
        extracted_text=extracted_text,
        project_id=project_id,
    )

    extracted_confidence = extraction.get("confidence")
    if isinstance(extracted_confidence, (int, float)):
        record.confidence_score = max(0.0, min(float(extracted_confidence), 1.0))

    reconciled = external_ingest.reconcile_records([record])
    if not reconciled:
        return "No ingestible document records found after reconciliation."

    saved_id = await vector_db.upsert_external_record(reconciled[0], user_id=user["id"])
    if not saved_id:
        return "Failed to persist document into memory."

    return (
        f"Document ingested successfully.\n"
        f"- Record ID: {saved_id}\n"
        f"- Source: {reconciled[0].source_uri}\n"
        f"- Domain: {reconciled[0].domain}\n"
        f"- Confidence: {reconciled[0].confidence_score:.2f}\n"
        f"- Entities extracted: {', '.join(reconciled[0].entities[:8]) or 'none'}"
    )


@mcp.tool()
@_track_mcp_tool("get_codebase_overview")
async def get_codebase_overview(api_key: str | None = None, max_items: int = 8) -> str:
    """Level 1 context: ultra-compressed overview of recent development activity."""
    user, _normalized_query, _safe_top_k, error = _authenticate_request(api_key=api_key, query="overview", top_k=max_items)
    if error:
        return error

    limit = max(3, min(int(max_items), int(settings.mcp_max_top_k)))
    user_id = user["id"]
    timeline = await vector_db.get_snapshot_timeline(limit=limit, user_id=user_id)
    if not timeline:
        return "No recent codebase memory available."

    file_counter = Counter()
    branch_counter = Counter()
    entity_counter = Counter()
    summary_samples: list[str] = []

    for snapshot in timeline:
        file_counter[str(snapshot.get("active_file") or "unknown")] += 1
        branch_counter[str(snapshot.get("git_branch") or "unknown")] += 1
        for entity in _parse_entities(snapshot.get("entities")):
            entity_counter[entity] += 1
        summary = str(snapshot.get("summary") or "").strip()
        if summary and len(summary_samples) < 3:
            summary_samples.append(summary)

    top_files = ", ".join([f"{name} ({count})" for name, count in file_counter.most_common(3)]) or "none"
    top_branches = ", ".join([f"{name} ({count})" for name, count in branch_counter.most_common(2)]) or "none"
    top_entities = ", ".join([name for name, _count in entity_counter.most_common(4)]) or "none"

    return (
        "Codebase overview:\n"
        f"- Recent snapshots analyzed: {len(timeline)}\n"
        f"- Hot files: {top_files}\n"
        f"- Active branches: {top_branches}\n"
        f"- Frequent entities: {top_entities}\n"
        f"- Current work themes: {' | '.join(summary_samples) if summary_samples else 'No summaries available'}"
    )


@mcp.tool()
@_track_mcp_tool("get_domain_context")
async def get_domain_context(domain: str, api_key: str | None = None, top_k: int | None = None) -> str:
    """Level 2 context: domain-focused summary with key decisions and known work streams."""
    normalized_domain = (domain or "").strip()
    if not normalized_domain:
        return "Invalid request: domain must be non-empty."

    user, _normalized_query, safe_top_k, error = _authenticate_request(api_key=api_key, query=normalized_domain, top_k=top_k)
    if error:
        return error

    results = await vector_db.semantic_search(normalized_domain, top_k=safe_top_k, user_id=user["id"])
    if not results:
        return f"No domain context found for '{normalized_domain}'."

    summaries = [str(item.get("summary") or "").strip() for item in results if str(item.get("summary") or "").strip()]
    branches = [str(item.get("git_branch") or "unknown") for item in results]
    files = [str(item.get("active_file") or "unknown") for item in results]

    decisions = " | ".join(summaries[:4]) if summaries else "No explicit decision summaries available"
    top_branches = ", ".join([name for name, _count in Counter(branches).most_common(3)])
    top_files = ", ".join([name for name, _count in Counter(files).most_common(3)])

    return (
        f"Domain context for '{normalized_domain}':\n"
        f"- Retrieved snapshots: {len(results)}\n"
        f"- Key decisions/work streams: {decisions}\n"
        f"- Frequent files: {top_files or 'none'}\n"
        f"- Active branches: {top_branches or 'none'}"
    )


@mcp.tool()
@_track_mcp_tool("get_function_context")
async def get_function_context(file: str, function: str, api_key: str | None = None, top_k: int | None = None) -> str:
    """Level 3 context: function/file-centric memory and decision history."""
    normalized_file = (file or "").strip()
    normalized_function = (function or "").strip()
    if not normalized_file or not normalized_function:
        return "Invalid request: both file and function are required."

    query = f"{normalized_file} {normalized_function}"
    user, _normalized_query, safe_top_k, error = _authenticate_request(api_key=api_key, query=query, top_k=top_k)
    if error:
        return error

    results = await vector_db.semantic_search(query, top_k=max(safe_top_k, 5), user_id=user["id"])
    if not results:
        return f"No function context found for {normalized_function} in {normalized_file}."

    needle_file = normalized_file.lower()
    needle_fn = normalized_function.lower()
    filtered: list[dict] = []
    for item in results:
        active_file = str(item.get("active_file") or "").lower()
        active_symbol = str(item.get("active_symbol") or "").lower()
        summary = str(item.get("summary") or "").lower()
        code = str(item.get("shadow_graph") or "").lower()
        if needle_file in active_file or needle_fn in active_symbol or needle_fn in summary or needle_fn in code:
            filtered.append(item)

    relevant = filtered[:safe_top_k] if filtered else results[:safe_top_k]
    output = [f"Function context for {normalized_function} in {normalized_file} (snapshots: {len(relevant)}):\n"]
    for idx, item in enumerate(relevant, 1):
        output.append(f"--- Match {idx} ---\n{_format_snapshot_block(item, include_code_chars=500)}")
    return "\n".join(output)


@mcp.tool()
@_track_mcp_tool("get_raw_snapshots")
async def get_raw_snapshots(
    query: str,
    max_tokens: int = 1000,
    api_key: str | None = None,
    top_k: int | None = None,
) -> str:
    """Level 4 context: raw snapshot retrieval controlled by approximate token budget."""
    user, normalized_query, safe_top_k, error = _authenticate_request(api_key=api_key, query=query, top_k=top_k)
    if error:
        return error

    char_budget = _approx_chars_for_tokens(max_tokens)
    results = await vector_db.semantic_search(normalized_query, top_k=safe_top_k, user_id=user["id"])
    if not results:
        return f"No raw snapshots found for query '{normalized_query}'."

    output_parts = [f"Raw snapshots for '{normalized_query}' (token budget~{max_tokens}):\n"]
    used_chars = len(output_parts[0])
    included = 0
    for item in results:
        block = f"--- Snapshot {included + 1} ---\n{_format_snapshot_block(item, include_code_chars=1000)}"
        if used_chars + len(block) > char_budget and included > 0:
            break
        output_parts.append(block)
        used_chars += len(block)
        included += 1

    output_parts.append(f"\nIncluded {included} snapshot(s) within budget.")
    return "\n".join(output_parts)


@mcp.tool()
@_track_mcp_tool("get_related_context")
async def get_related_context(
    anchor: str,
    relationship_types: list[str] | None = None,
    api_key: str | None = None,
    depth: int = 1,
    max_tokens: int = 1000,
    top_k: int | None = None,
) -> str:
    """Traverse related memory context for an anchor via co-changed/co-debugged/causal relationships."""
    normalized_anchor = _pick_entity_anchor(anchor)
    if not normalized_anchor:
        return "Invalid request: anchor must be non-empty."

    user, _normalized_query, safe_top_k, error = _authenticate_request(api_key=api_key, query=anchor, top_k=top_k)
    if error:
        return error

    max_depth = max(1, min(int(depth), 3))
    char_budget = _approx_chars_for_tokens(max_tokens)
    max_neighbors = max(2, min(safe_top_k, 8))
    preferred_relationships = {str(rel).strip().lower() for rel in (relationship_types or []) if str(rel).strip()}

    seed_results = await vector_db.semantic_search(anchor, top_k=max(safe_top_k * 2, 8), user_id=user["id"])
    if not seed_results:
        return f"No related context found for anchor '{anchor}'."

    graph: dict[str, set[str]] = defaultdict(set)
    supporting_snapshots: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for meta in seed_results:
        entities = [e.strip().lower() for e in _parse_entities(meta.get("entities"))]
        if not entities:
            active_symbol = str(meta.get("active_symbol") or "").strip().lower()
            if active_symbol:
                entities = [active_symbol]

        if not entities:
            continue

        for entity in entities:
            for other in entities:
                if entity == other:
                    continue
                graph[entity].add(other)
                supporting_snapshots[(entity, other)].append(meta)

    if normalized_anchor not in graph:
        # fallback: use top entity from results as anchor pivot
        if graph:
            normalized_anchor = next(iter(graph.keys()))
        else:
            return f"No relationship graph available for anchor '{anchor}'."

    lines = [
        f"Related context for '{anchor}' (resolved anchor: {normalized_anchor})",
        f"Depth: {max_depth}, Relationship filter: {', '.join(sorted(preferred_relationships)) if preferred_relationships else 'all'}, Budget~{max_tokens} tokens",
    ]
    used_chars = sum(len(line) for line in lines)

    visited: set[str] = {normalized_anchor}
    frontier = [(normalized_anchor, 0)]

    while frontier:
        current, level = frontier.pop(0)
        if level >= max_depth:
            continue

        neighbors = sorted(graph.get(current, set()))[:max_neighbors]
        if not neighbors:
            continue

        lines.append(f"\nLevel {level + 1} from {current}:")
        used_chars += len(lines[-1])

        for neighbor in neighbors:
            snaps = supporting_snapshots.get((current, neighbor), [])
            rel_type, rel_score = _classify_relationship(
                current,
                neighbor,
                snaps,
                preferred=preferred_relationships,
            )

            if preferred_relationships and rel_type not in preferred_relationships:
                continue

            summary = ""
            if snaps:
                summary = str(snaps[0].get("summary") or "").strip()
            line = f"- {neighbor} [{rel_type}] score={rel_score}" + (f" | {summary}" if summary else "")

            if used_chars + len(line) > char_budget:
                lines.append("\n[Traversal truncated due to token budget]")
                return "\n".join(lines)

            lines.append(line)
            used_chars += len(line)

            if neighbor not in visited:
                visited.add(neighbor)
                frontier.append((neighbor, level + 1))

    lines.append(f"\nDiscovered nodes: {len(visited)}")
    _mcp_metrics["graph_discovered_nodes"].append(len(visited))
    return "\n".join(lines)


@mcp.tool()
@_track_mcp_tool("get_context_for_task_type")
async def get_context_for_task_type(
    domain: str,
    task_type: str,
    project_id: str | None = None,
    api_key: str | None = None,
    max_tokens: int | None = None,
    top_k: int | None = None,
) -> str:
    """Return cached task-scoped context for a domain, with freshness-aware fallback synthesis."""
    normalized_domain = (domain or "").strip()
    normalized_task_type = (task_type or "").strip().lower()
    if not normalized_domain:
        return "Invalid request: domain must be non-empty."
    if normalized_task_type not in _TASK_TYPES:
        return (
            "Invalid request: task_type must be one of "
            "debugging, code-review, feature-addition, incident-response."
        )

    query = f"{normalized_domain} {normalized_task_type}"
    user, _normalized_query, safe_top_k, error = _authenticate_request(api_key=api_key, query=query, top_k=top_k)
    if error:
        return error

    user_id = str(user["id"])
    normalized_project_id = (project_id or "").strip()
    safe_max_tokens = int(max_tokens if max_tokens is not None else settings.mcp_task_summary_default_max_tokens)
    safe_max_tokens = max(300, min(safe_max_tokens, 4000))

    cache_enabled = bool(settings.mcp_task_summary_cache_enabled)
    ttl_seconds = max(30, int(settings.mcp_task_summary_ttl_seconds))
    cache_key = (user_id, normalized_domain.lower(), normalized_task_type, normalized_project_id)
    now = time.time()

    results = await vector_db.semantic_search(
        query,
        top_k=max(safe_top_k, 6),
        user_id=user["id"],
        project_id=normalized_project_id or None,
    )

    fingerprint = _build_snapshot_fingerprint(results)
    cached = _task_summary_cache.get(cache_key) if cache_enabled else None

    cache_status = "MISS"
    if cached:
        is_expired = now >= float(cached.get("expires_at", 0))
        is_fresh_match = cached.get("fingerprint") == fingerprint
        if not is_expired and is_fresh_match:
            cache_status = "HIT"
            _mcp_metrics["task_cache_hit"] += 1
            age_seconds = max(0, int(now - float(cached.get("generated_at_ts", now))))
            payload = str(cached.get("content") or "")
            response = (
                f"{payload}\n"
                f"\nFreshness: cache_status={cache_status}, age_seconds={age_seconds}, "
                f"generated_at={cached.get('generated_at', 'unknown')}, ttl_seconds={ttl_seconds}"
            )
            return _trim_to_budget(response, safe_max_tokens)
        cache_status = "STALE_REBUILT"
        _mcp_metrics["task_cache_stale_rebuilt"] += 1
    else:
        _mcp_metrics["task_cache_miss"] += 1

    generated_at = datetime.now(timezone.utc)
    synthesized = _summarize_task_context(normalized_domain, normalized_task_type, results)
    metadata = (
        f"\n\nFreshness: cache_status={cache_status}, generated_at={generated_at.isoformat()}, "
        f"snapshot_fingerprint={fingerprint}, snapshots={len(results)}, ttl_seconds={ttl_seconds}"
    )
    response = _trim_to_budget(synthesized + metadata, safe_max_tokens)

    if cache_enabled:
        _task_summary_cache[cache_key] = {
            "content": synthesized,
            "fingerprint": fingerprint,
            "generated_at": generated_at.isoformat(),
            "generated_at_ts": now,
            "expires_at": now + ttl_seconds,
        }

    return response


@mcp.tool()
@_track_mcp_tool("get_incident_packet")
async def get_incident_packet(
    question: str,
    api_key: str | None = None,
    project_id: str | None = None,
    time_window: str = "24h",
) -> str:
    """Build a concise, contradiction-aware incident packet for external AI agents."""
    user, normalized_query, safe_top_k, error = _authenticate_request(api_key=api_key, query=question, top_k=top_k_from_time_window(time_window))
    if error:
        return error

    user_id = user["id"]
    snapshots = await vector_db.semantic_search(
        normalized_query,
        top_k=max(3, safe_top_k),
        user_id=user_id,
        project_id=(project_id or None),
    )
    facts = await vector_db.recall_facts(normalized_query, top_k=3, user_id=user_id, min_salience=0.3)

    normalized_facts = [
        {
            "id": str(fact.get("id") or f"fact_{index + 1}"),
            "active_file": f"fact://{fact.get('kind') or 'memory'}",
            "git_branch": "knowledge",
            "timestamp": str(fact.get("created_at") or datetime.now(timezone.utc).isoformat()),
            "summary": str(fact.get("document") or fact.get("content") or ""),
            "source_type": "fact",
            "source_id": str(fact.get("id") or ""),
            "source_uri": "",
        }
        for index, fact in enumerate(facts)
    ]

    evidence_graph = incident_archaeology.build_evidence_graph(snapshots + normalized_facts)
    hypotheses = incident_archaeology.rank_hypotheses(evidence_graph)
    contradictions = incident_archaeology.build_contradictions(evidence_graph)
    disproof_checks = incident_archaeology.build_disproof_checks(hypotheses)
    recovery_options = incident_archaeology.simulate_recovery_options(hypotheses)
    confidence = incident_archaeology.compute_confidence(
        coverage=float(evidence_graph.get("coverage") or 0.0),
        recency=float(evidence_graph.get("recency") or 0.5),
        contradiction_count=len(contradictions),
        evidence_count=len(evidence_graph.get("nodes") or []),
    )

    lines: list[str] = [
        f"Incident Packet ({time_window})",
        f"Question: {normalized_query}",
        f"Confidence: {confidence:.2f}",
        "",
        "Hypotheses:",
    ]
    if hypotheses:
        for hypothesis in hypotheses[:3]:
            lines.append(
                f"- #{hypothesis.get('rank')} {hypothesis.get('cause')} "
                f"(confidence={hypothesis.get('confidence')}, evidence={', '.join(hypothesis.get('supportingEvidenceIds') or []) or 'none'})"
            )
    else:
        lines.append("- No stable hypotheses generated.")

    lines.extend(["", "Recovery Options:"])
    if recovery_options:
        for option in recovery_options[:3]:
            lines.append(
                f"- {option.get('strategy')}: risk={option.get('risk')}, blast={option.get('blastRadius')}, "
                f"eta={option.get('estimatedTimeMinutes')}m, commands={', '.join(option.get('commands') or []) or 'none'}"
            )
    else:
        lines.append("- No recovery options generated.")

    lines.extend(["", "Contradictions:"])
    if contradictions:
        lines.extend([f"- {item}" for item in contradictions[:5]])
    else:
        lines.append("- None observed.")

    lines.extend(["", "Disproof Checks:"])
    if disproof_checks:
        lines.extend([f"- {item}" for item in disproof_checks[:5]])
    else:
        lines.append("- Add targeted falsification tests for each hypothesis.")

    lines.extend(["", "Evidence IDs:"])
    evidence_ids = [str(item.get("id")) for item in (evidence_graph.get("nodes") or [])[:8]]
    lines.append(f"- {', '.join(evidence_ids) if evidence_ids else 'none'}")

    return _trim_to_budget("\n".join(lines), max_tokens=1200)


def top_k_from_time_window(time_window: str) -> int:
    normalized = (time_window or "24h").strip().lower()
    if normalized in {"1h", "2h", "6h"}:
        return 4
    if normalized in {"12h", "24h"}:
        return 6
    return 8


@mcp.tool()
@_track_mcp_tool("get_mcp_metrics")
async def get_mcp_metrics(api_key: str | None = None) -> str:
    """Return MCP observability metrics including latency percentiles and key safety counters."""
    user, _normalized_query, _safe_top_k, error = _authenticate_request(api_key=api_key, query="metrics", top_k=1)
    if error:
        return error

    del user
    uptime_seconds = max(0, int(time.time() - float(_mcp_metrics["started_at"])))
    total = int(_mcp_metrics["requests_total"])
    success = int(_mcp_metrics["success_total"])
    errors = int(_mcp_metrics["error_total"])

    per_tool_lines: list[str] = []
    for tool_name, count in _mcp_metrics["tool_counts"].most_common():
        samples = list(_mcp_metrics["tool_latency_ms"].get(tool_name, []))
        p50 = _percentile(samples, 50)
        p95 = _percentile(samples, 95)
        p99 = _percentile(samples, 99)
        per_tool_lines.append(
            f"- {tool_name}: calls={count}, latency_ms(p50/p95/p99)={p50:.1f}/{p95:.1f}/{p99:.1f}"
        )

    graph_samples = list(_mcp_metrics["graph_discovered_nodes"])
    avg_graph_nodes = (sum(graph_samples) / len(graph_samples)) if graph_samples else 0.0

    return "\n".join(
        [
            "MCP Metrics:",
            f"- Uptime seconds: {uptime_seconds}",
            f"- Requests total: {total}",
            f"- Success total: {success}",
            f"- Error total: {errors}",
            f"- Auth failures: {int(_mcp_metrics['auth_failures'])}",
            f"- Rate limited: {int(_mcp_metrics['rate_limited'])}",
            f"- Oversized rejected: {int(_mcp_metrics['oversized_rejections'])}",
            f"- Task summary cache hit/miss/stale: {int(_mcp_metrics['task_cache_hit'])}/{int(_mcp_metrics['task_cache_miss'])}/{int(_mcp_metrics['task_cache_stale_rebuilt'])}",
            f"- Graph discovered nodes avg: {avg_graph_nodes:.2f}",
            "Per-tool metrics:",
            *(per_tool_lines or ["- No tool calls recorded yet."]),
        ]
    )


@mcp.tool()
@_track_mcp_tool("get_mcp_readiness")
async def get_mcp_readiness(api_key: str | None = None) -> str:
    """Check MCP runtime readiness for auth, vector storage, and ingestion subsystems."""
    user, _normalized_query, _safe_top_k, error = _authenticate_request(api_key=api_key, query="readiness", top_k=1)
    if error:
        return error

    checks: list[tuple[str, bool, str]] = []

    checks.append(("auth", bool(user and user.get("id")), "principal resolved" if user and user.get("id") else "principal missing"))
    checks.append(("vector_client", bool(getattr(vector_db, "chroma_client", None)), "chroma client initialized" if getattr(vector_db, "chroma_client", None) else "chroma unavailable"))

    try:
        collection_ok = vector_db._get_collection(user.get("id")) is not None
    except Exception:
        collection_ok = False
    checks.append(("vector_collection", collection_ok, "collection available" if collection_ok else "collection unavailable"))

    checks.append(("external_ingestion", bool(settings.mcp_external_ingestion_enabled), "enabled" if settings.mcp_external_ingestion_enabled else "disabled"))
    checks.append(("slack_ingestion", bool(settings.mcp_external_slack_enabled), "enabled" if settings.mcp_external_slack_enabled else "disabled"))

    ready = all(flag for _name, flag, _details in checks[:3])
    status = "READY" if ready else "DEGRADED"
    lines = [f"MCP readiness: {status}"]
    for name, flag, details in checks:
        lines.append(f"- {name}: {'ok' if flag else 'not-ready'} ({details})")
    return "\n".join(lines)

if __name__ == "__main__":
    logger.info("Starting SecondCortex MCP Server via stdio...")
    mcp.run()
