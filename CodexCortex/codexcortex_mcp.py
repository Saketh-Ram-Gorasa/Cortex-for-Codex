from __future__ import annotations

import json
import logging
import os
import re
import sys
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import anyio
import mcp.types as mcp_types
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.server.fastmcp import FastMCP
from mcp.shared.message import SessionMessage


logger = logging.getLogger("codexcortex.mcp")
logging.basicConfig(level=os.getenv("CODEXCORTEX_LOG_LEVEL", "INFO"))


def _configure_backend_path() -> Path:
    backend_path = os.getenv("SECONDCORTEX_BACKEND_PATH", "").strip()
    if backend_path:
        resolved = Path(backend_path).expanduser().resolve()
    else:
        resolved = (Path(__file__).resolve().parents[1] / "secondcortex-backend").resolve()

    if str(resolved) not in sys.path:
        sys.path.insert(0, str(resolved))
    return resolved


BACKEND_PATH = _configure_backend_path()

try:
    from auth.database import UserDB
    from services.external_ingest import ExternalMemoryRecord
    from services.vector_db import VectorDBService
except Exception as exc:  # pragma: no cover - import-time guard for CLI users
    raise RuntimeError(
        "CodexCortex could not import SecondCortex backend modules. "
        "Set SECONDCORTEX_BACKEND_PATH to the secondcortex-backend directory."
    ) from exc


mcp = FastMCP("CodexCortex")
user_db: Any | None = None
vector_db: Any | None = None


def _get_user_db() -> Any:
    global user_db
    if user_db is None:
        user_db = UserDB()
    return user_db


def _get_vector_db() -> Any:
    global vector_db
    if vector_db is None:
        vector_db = VectorDBService()
    return vector_db


def _resolve_api_key(api_key: str | None = None) -> str | None:
    return (api_key or os.getenv("SECONDCORTEX_MCP_API_KEY") or "").strip() or None


def _authenticate(api_key: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    resolved = _resolve_api_key(api_key)
    if not resolved:
        return None, "Authentication required: set SECONDCORTEX_MCP_API_KEY or pass api_key."

    try:
        user = _get_user_db().get_user_by_mcp_api_key(resolved)
    except Exception as exc:
        logger.exception("MCP key lookup failed")
        return None, f"Authentication failed: key lookup error ({exc})."

    if not user:
        return None, "Authentication failed: invalid or revoked MCP API key."
    return dict(user), None


def _safe_int(value: int | None, default: int, lower: int, upper: int) -> int:
    try:
        parsed = int(value if value is not None else default)
    except Exception:
        parsed = default
    return max(lower, min(parsed, upper))


def _clamp_confidence(value: float | int | None) -> float:
    try:
        parsed = float(value if value is not None else 0.7)
    except Exception:
        parsed = 0.7
    return max(0.0, min(parsed, 1.0))


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_tags(tags: list[str] | None) -> list[str]:
    output: list[str] = []
    for tag in tags or []:
        cleaned = re.sub(r"[^a-zA-Z0-9_.:/-]+", "_", str(tag).strip().lower())
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return output[:8]


def _snapshot_id(item: dict[str, Any]) -> str:
    return _normalize_text(item.get("id") or item.get("source_id") or item.get("snapshot_id"))


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    raw = _normalize_text(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _path_matches(snapshot_path: Any, requested_path: str | None) -> bool:
    requested = _normalize_text(requested_path).replace("\\", "/").lower()
    if not requested:
        return True

    observed = _normalize_text(snapshot_path).replace("\\", "/").lower()
    if not observed:
        return False
    return observed == requested or observed.endswith(f"/{requested}") or requested.endswith(f"/{observed}")


def _decision_payload_from_item(item: dict[str, Any]) -> dict[str, Any]:
    for key in ("shadow_graph", "content", "document"):
        raw = _normalize_text(item.get(key))
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _format_snapshot(item: dict[str, Any], index: int, include_id_hint: bool = True) -> str:
    decision_payload = _decision_payload_from_item(item)
    lines = [
        f"--- Snapshot {index} ---",
        f"Time: {_normalize_text(item.get('timestamp')) or 'unknown'}",
        f"File: {_normalize_text(item.get('active_file')) or 'unknown'}",
        f"Branch: {_normalize_text(item.get('git_branch')) or 'unknown'}",
        f"Summary: {_normalize_text(item.get('summary')) or 'no summary'}",
    ]

    source_type = _normalize_text(item.get("source_type"))
    source_uri = _normalize_text(item.get("source_uri"))
    confidence = item.get("confidence_score", item.get("confidence"))
    if source_type:
        lines.append(f"Source: {source_type}")
    if source_uri:
        lines.append(f"Source URI: {source_uri}")
    if confidence is not None:
        lines.append(f"Confidence: {_clamp_confidence(confidence):.2f}")

    sid = _snapshot_id(item)
    if include_id_hint and sid:
        lines.append(f"ID: {sid}")

    task_prompt = _normalize_text(decision_payload.get("task_prompt"))
    if task_prompt:
        lines.append(f"Task: {task_prompt}")

    files_modified = decision_payload.get("files_modified")
    if isinstance(files_modified, list) and files_modified:
        lines.append(f"Files modified: {', '.join(str(path) for path in files_modified[:8])}")

    tags = decision_payload.get("tags")
    if isinstance(tags, list) and tags:
        lines.append(f"Tags: {', '.join(str(tag) for tag in tags[:8])}")

    entities = item.get("entities")
    if entities:
        if isinstance(entities, list):
            entity_text = ", ".join(str(entity) for entity in entities[:10])
        else:
            entity_text = _normalize_text(entities)
        lines.append(f"Entities: {entity_text}")

    parent = _normalize_text(item.get("parent_snapshot_id") or decision_payload.get("parent_snapshot_id"))
    if parent:
        lines.append(f"Parent: {parent}")

    contradictions = _normalize_text(item.get("contradictions") or decision_payload.get("contradictions"))
    if contradictions:
        lines.append(f"Contradictions: {contradictions}")

    return "\n".join(lines)


@mcp.tool()
async def search_memory(query: str, api_key: str | None = None, top_k: int | None = None) -> str:
    """Search SecondCortex memory for relevant prior decisions before editing code."""
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return "Invalid request: query must be non-empty."

    user, error = _authenticate(api_key)
    if error:
        return error

    safe_top_k = _safe_int(top_k, default=5, lower=1, upper=10)
    results = await _get_vector_db().semantic_search(normalized_query, top_k=safe_top_k, user_id=str(user["id"]))
    if not results:
        return f"No memory found for '{normalized_query}'."

    lines = [f"Found {len(results)} memory result(s) for '{normalized_query}':"]
    for index, item in enumerate(results, 1):
        lines.append(_format_snapshot(dict(item), index))
    return "\n\n".join(lines)


@mcp.tool()
async def get_decision_context(target: str, api_key: str | None = None, depth: int = 3) -> str:
    """Retrieve decision context for a file, function, symbol, snapshot, or prior decision target."""
    normalized_target = _normalize_text(target)
    if not normalized_target:
        return "Invalid request: target must be non-empty."

    user, error = _authenticate(api_key)
    if error:
        return error

    safe_depth = _safe_int(depth, default=3, lower=1, upper=10)
    top_k = min(max(safe_depth * 2, 4), 10)
    results = await _get_vector_db().semantic_search(
        f"decision context history rationale {normalized_target}",
        top_k=top_k,
        user_id=str(user["id"]),
    )
    if not results:
        return f"No decision context found for '{normalized_target}'."

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in results:
        item = dict(raw)
        key = _snapshot_id(item) or f"{item.get('timestamp')}::{item.get('active_file')}::{item.get('summary')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= top_k:
            break

    lines = [
        f"Decision context for '{normalized_target}' (depth={safe_depth}, results={len(deduped)}):",
        "Use any listed ID as parent_snapshot_id when your work extends or supersedes that decision.",
    ]
    for index, item in enumerate(deduped, 1):
        lines.append(_format_snapshot(item, index))
    return "\n\n".join(lines)


@mcp.tool()
async def list_snapshots(
    file_path: str | None = None,
    api_key: str | None = None,
    limit: int = 10,
    since_hours: int = 168,
) -> str:
    """List recent SecondCortex snapshots, optionally filtered by file path and recency."""
    user, error = _authenticate(api_key)
    if error:
        return error

    safe_limit = _safe_int(limit, default=10, lower=1, upper=50)
    safe_since_hours = _safe_int(since_hours, default=168, lower=1, upper=24 * 90)
    fetch_limit = min(max(safe_limit * 4, 50), 500)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=safe_since_hours)

    timeline = await _get_vector_db().get_snapshot_timeline(limit=fetch_limit, user_id=str(user["id"]))
    filtered: list[dict[str, Any]] = []
    for raw in timeline:
        item = dict(raw)
        parsed_ts = _parse_timestamp(item.get("timestamp"))
        if parsed_ts and parsed_ts < cutoff:
            continue
        if not _path_matches(item.get("active_file"), file_path):
            continue
        filtered.append(item)
        if len(filtered) >= safe_limit:
            break

    scope = f" for {file_path}" if _normalize_text(file_path) else ""
    if not filtered:
        return f"No snapshots found{scope} in the last {safe_since_hours} hour(s)."

    lines = [f"Recent snapshots{scope} (showing {len(filtered)} of max {safe_limit}):"]
    for index, item in enumerate(filtered, 1):
        lines.append(_format_snapshot(item, index))
    return "\n\n".join(lines)


@mcp.tool()
async def store_decision(
    task_prompt: str,
    reasoning: str,
    files_modified: list[str],
    confidence: float = 0.7,
    tags: list[str] | None = None,
    parent_snapshot_id: str | None = None,
    contradictions: str | None = None,
    api_key: str | None = None,
) -> str:
    """Store a Codex decision snapshot after completing a coding task."""
    normalized_task = _normalize_text(task_prompt)
    normalized_reasoning = _normalize_text(reasoning)
    normalized_files = [_normalize_text(path) for path in (files_modified or []) if _normalize_text(path)]
    if not normalized_task:
        return "Invalid request: task_prompt is required."
    if not normalized_reasoning:
        return "Invalid request: reasoning is required."
    if not normalized_files:
        return "Invalid request: files_modified must include at least one file path."

    user, error = _authenticate(api_key)
    if error:
        return error

    safe_confidence = _clamp_confidence(confidence)
    safe_tags = _normalize_tags(tags)
    parent = _normalize_text(parent_snapshot_id)
    contradiction_text = _normalize_text(contradictions)

    content_payload = {
        "task_prompt": normalized_task,
        "reasoning": normalized_reasoning,
        "files_modified": normalized_files,
        "confidence": safe_confidence,
        "tags": safe_tags,
        "parent_snapshot_id": parent,
        "contradictions": contradiction_text,
        "agent": "codex",
    }
    title = f"Codex decision: {normalized_task[:80]}"
    summary = normalized_reasoning[:220]
    entities = [item for item in dict.fromkeys([*safe_tags, *normalized_files, parent]) if item][:20]
    source_digest = hashlib.sha256(json.dumps(content_payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    record = ExternalMemoryRecord(
        source_type="codex_decision",
        source_id=f"codex_decision:{source_digest}",
        source_uri=f"codexcortex://decision/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        domain="codex",
        title=title,
        summary=summary,
        content=json.dumps(content_payload, indent=2, sort_keys=True),
        entities=entities,
        confidence_score=safe_confidence,
        timestamp=datetime.now(timezone.utc),
        project_id=None,
    )

    saved_id = await _get_vector_db().upsert_external_record(record, user_id=str(user["id"]))
    if not saved_id:
        return "Failed to store Codex decision in SecondCortex memory."

    return (
        "Codex decision stored successfully.\n"
        f"- Record ID: {saved_id}\n"
        f"- Confidence: {safe_confidence:.2f}\n"
        f"- Files: {', '.join(normalized_files)}\n"
        f"- Parent snapshot: {parent or 'none'}"
    )


@mcp.tool()
async def get_mcp_readiness(api_key: str | None = None) -> str:
    """Check CodexCortex auth and vector storage readiness."""
    user, error = _authenticate(api_key)
    auth_ok = error is None and user is not None
    db = _get_vector_db()
    vector_client_ok = bool(getattr(db, "chroma_client", None))

    collection_ok = False
    if auth_ok:
        try:
            collection_ok = db._get_collection(str(user["id"])) is not None
        except Exception:
            collection_ok = False

    status = "READY" if auth_ok and vector_client_ok and collection_ok else "DEGRADED"
    lines = [
        f"CodexCortex readiness: {status}",
        f"- backend_path: {BACKEND_PATH}",
        f"- auth: {'ok' if auth_ok else 'not-ready'} ({'principal resolved' if auth_ok else error})",
        f"- vector_client: {'ok' if vector_client_ok else 'not-ready'}",
        f"- vector_collection: {'ok' if collection_ok else 'not-ready'}",
    ]
    return "\n".join(lines)


def _find_header_terminator(buffer: bytes) -> tuple[int, int]:
    crlf = buffer.find(b"\r\n\r\n")
    if crlf != -1:
        return crlf, 4
    lf = buffer.find(b"\n\n")
    if lf != -1:
        return lf, 2
    return -1, 0


def _parse_content_length(header_blob: bytes) -> int | None:
    normalized = header_blob.replace(b"\r\n", b"\n")
    for raw_line in normalized.split(b"\n"):
        line = raw_line.strip()
        if not line or b":" not in line:
            continue
        key, value = line.split(b":", 1)
        if key.strip().lower() != b"content-length":
            continue
        try:
            parsed = int(value.strip())
            if parsed >= 0:
                return parsed
        except ValueError:
            return None
    return None


@asynccontextmanager
async def _compat_stdio_server(
    stdin: anyio.AsyncFile[bytes] | None = None,
    stdout: anyio.AsyncFile[bytes] | None = None,
):
    if not stdin:
        stdin = anyio.wrap_file(sys.stdin.buffer)
    if not stdout:
        stdout = anyio.wrap_file(sys.stdout.buffer)

    read_stream: MemoryObjectReceiveStream[SessionMessage | Exception]
    read_stream_writer: MemoryObjectSendStream[SessionMessage | Exception]
    write_stream: MemoryObjectSendStream[SessionMessage]
    write_stream_reader: MemoryObjectReceiveStream[SessionMessage]
    read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
    write_stream, write_stream_reader = anyio.create_memory_object_stream(0)
    transport_mode = {"detected": False, "content_length": True}

    async def stdin_reader() -> None:
        buffer = b""
        try:
            async with read_stream_writer:
                while True:
                    chunk = await stdin.read(1)
                    if not chunk:
                        break
                    if isinstance(chunk, str):
                        chunk = chunk.encode("utf-8")
                    buffer += chunk

                    while buffer:
                        buffer = buffer.lstrip(b"\r\n\t ")
                        if not buffer:
                            break

                        if buffer[:15].lower() == b"content-length:":
                            header_end, sep_len = _find_header_terminator(buffer)
                            if header_end < 0:
                                break
                            header = buffer[:header_end]
                            payload_start = header_end + sep_len
                            payload_length = _parse_content_length(header)
                            if payload_length is None:
                                buffer = buffer[payload_start:]
                                continue
                            if len(buffer) < payload_start + payload_length:
                                break

                            payload = buffer[payload_start : payload_start + payload_length]
                            buffer = buffer[payload_start + payload_length :]
                            try:
                                message = mcp_types.JSONRPCMessage.model_validate_json(payload.decode("utf-8"))
                            except Exception as exc:
                                await read_stream_writer.send(exc)
                                continue
                            transport_mode["detected"] = True
                            transport_mode["content_length"] = True
                            await read_stream_writer.send(SessionMessage(message))
                            continue

                        newline_idx = buffer.find(b"\n")
                        if newline_idx < 0:
                            break
                        line = buffer[: newline_idx + 1].strip()
                        buffer = buffer[newline_idx + 1 :]
                        if not line:
                            continue
                        try:
                            message = mcp_types.JSONRPCMessage.model_validate_json(line.decode("utf-8"))
                        except Exception as exc:
                            await read_stream_writer.send(exc)
                            continue
                        transport_mode["detected"] = True
                        transport_mode["content_length"] = False
                        await read_stream_writer.send(SessionMessage(message))
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()

    async def stdout_writer() -> None:
        try:
            async with write_stream_reader:
                async for session_message in write_stream_reader:
                    payload = session_message.message.model_dump_json(by_alias=True, exclude_none=True).encode("utf-8")
                    if transport_mode["content_length"]:
                        frame = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload
                    else:
                        frame = payload + b"\n"
                    await stdout.write(frame)
                    await stdout.flush()
        except anyio.ClosedResourceError:
            await anyio.lowlevel.checkpoint()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(stdin_reader)
        task_group.start_soon(stdout_writer)
        yield read_stream, write_stream


async def _run_mcp_compat_stdio() -> None:
    async with _compat_stdio_server() as (read_stream, write_stream):
        await mcp._mcp_server.run(  # noqa: SLF001
            read_stream,
            write_stream,
            mcp._mcp_server.create_initialization_options(),  # noqa: SLF001
        )


def main() -> None:
    """Console entry point for installed CodexCortex MCP servers."""
    logger.info("Starting CodexCortex MCP server via stdio.")
    anyio.run(_run_mcp_compat_stdio)


if __name__ == "__main__":
    main()
