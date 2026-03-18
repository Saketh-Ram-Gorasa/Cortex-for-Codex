"""
SecondCortex Backend — FastAPI Main Server

Endpoints:
  POST /api/v1/auth/signup  — Create a new account.
  POST /api/v1/auth/login   — Log in and get a JWT token.
    POST /api/v1/ingest/git   — Retroactively ingest git history into memory.
  POST /api/v1/snapshot     — Receives sanitized IDE snapshots.
  POST /api/v1/query        — User question → Planner → Executor pipeline.
  POST /api/v1/resurrect    — Generate resurrection commands.
  GET  /api/v1/events       — Poll recent snapshots for the Live Graph.
  GET  /health              — Health check.
"""

import logging
import sys
import os
import re
import json
import time
import jwt
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

# ── Force Python to see the local directories (fixes Azure ModuleNotFoundError) ──────────
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ── ChromaDB Compatibility Patch for Azure (Older SQLite3) ────────────────────────────────
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Body
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
import traceback
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agents.executor import ExecutorAgent
from agents.planner import PlannerAgent
from agents.retriever import RetrieverAgent
from agents.simulator import SimulatorAgent
from auth.jwt_handler import get_current_user, verify_token
from auth.routes import router as auth_router
from config import settings
from models import schemas
from models.schemas import (
    QueryRequest,
    QueryResponse,
    ResurrectionRequest,
    ResurrectionResponse,
    ResurrectionCommand,
    SafetyReport,
    SnapshotPayload,
    ArchaeologyRequest,
    ArchaeologyResponse,
    ChatMessage,
    ChatHistoryResponse,
    MemoryMetadata,
    MemoryOperation,
    StoredSnapshot,
    RetroIngestRequest,
    RetroIngestResponse,
    EnrichedSnapshot,
)
from auth.routes import user_db
from services.vector_db import VectorDBService
from services.llm_client import create_llm_client, create_async_llm_client, get_chat_model
from services.git_ingest import RetroGitIngestionService
from pydantic import BaseModel, Field

SYNC_TOKEN_EXPIRY_SECONDS = 3600


class SyncSnapshotRow(BaseModel):
    id: str
    user_id: str
    team_id: str | None = None
    workspace: str
    active_file: str
    git_branch: str | None = None
    terminal_commands: str = "[]"
    summary: str = ""
    enriched_context: str = "{}"
    timestamp: int
    synced: int = 0


class SyncDataRequest(BaseModel):
    rows: list[SyncSnapshotRow] = Field(default_factory=list)

# ── Logging setup ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger("secondcortex.main")

# ── Application ─────────────────────────────────────────────────
app = FastAPI(
    title="SecondCortex API",
    description="Multi-Agent Orchestrator for IDE Context Memory",
    version="0.3.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://sc-frontend-suhaan.azurewebsites.net",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    err_msg = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error("GLOBAL EXCEPTION: %s", err_msg)
    
    # Attempt to write to a visible place in persistence if possible
    try:
        with open("/home/backend_error.log", "a") as f:
            f.write(f"\n--- {datetime.now()} ---\n")
            f.write(err_msg)
            f.write("\n")
    except:
        pass
        
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "traceback": err_msg if settings.host == "0.0.0.0" else "hidden"},
    )

# ── Include auth routes ─────────────────────────────────────────
app.include_router(auth_router)

# ── MCP Server Mount ──────────────────────────
from mcp_server import mcp

app.mount("/mcp", mcp.sse_app())

# ── Service & Agent Initialization ──────────────────────────────
vector_db = VectorDBService()
retriever = RetrieverAgent(vector_db)
planner = PlannerAgent(vector_db)
executor = ExecutorAgent()
simulator = SimulatorAgent()
archaeology_llm_client = create_llm_client()
archaeology_async_llm_client = create_async_llm_client()
git_ingestion = RetroGitIngestionService()

# Most recently received raw snapshot per user, updated immediately on /snapshot ingest.
_latest_ingested_snapshot: dict[str, dict[str, Any]] = {}


def _create_sync_token(user_id: str, team_id: str | None) -> str:
    payload = {
        "sub": user_id,
        "team_id": team_id,
        "kind": "powersync",
        "iat": int(time.time()),
        "exp": int(time.time()) + SYNC_TOKEN_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _verify_sync_token(token: str | None, user_id: str) -> bool:
    if not token:
        return False
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload.get("kind") == "powersync" and payload.get("sub") == user_id
    except Exception:
        return False


def _snapshot_payload_from_sync_row(row: SyncSnapshotRow) -> SnapshotPayload:
    terminal_commands: list[str] = []
    if row.terminal_commands:
        try:
            parsed = json.loads(row.terminal_commands)
            if isinstance(parsed, list):
                terminal_commands = [str(v) for v in parsed]
        except Exception:
            terminal_commands = []

    timestamp_dt = datetime.utcfromtimestamp(max(0, row.timestamp) / 1000)
    shadow_graph = row.summary or "Synced snapshot"
    if row.enriched_context and row.enriched_context.strip() not in ("", "{}"):
        try:
            parsed = json.loads(row.enriched_context)
            normalized = EnrichedSnapshot.model_validate(parsed)
            shadow_graph = normalized.model_dump_json(by_alias=True)
        except Exception:
            shadow_graph = row.enriched_context

    return SnapshotPayload(
        timestamp=timestamp_dt,
        workspaceFolder=row.workspace,
        activeFile=row.active_file,
        languageId="unknown",
        shadowGraph=shadow_graph,
        gitBranch=row.git_branch,
        terminalCommands=terminal_commands,
    )


def _is_latest_snapshot_question(question: str) -> bool:
    q = (question or "").strip().lower()
    if not q:
        return False

    # Multi-snapshot analysis should NOT take the single-latest fast path.
    has_multi_snapshot_intent = (
        bool(re.search(r"\b(last|recent|past)\s+\d+\s+snapshots?\b", q))
        or bool(re.search(r"\b(last|recent|past)\s+(one|two|three|four|five|six|seven|eight|nine|ten)\s+snapshots?\b", q))
        or bool(re.search(r"\b(summarize|summary|compare|across|history|timeline)\b", q))
    )
    if has_multi_snapshot_intent:
        return False

    has_recency = bool(
        re.search(
            r"\b("
            r"latest|newest|most recent|current|fetch latest|"
            r"last snapshot|recent snapshot"
            r")\b",
            q,
        )
    )
    has_context = bool(re.search(r"\b(snapshot|context|edited|editing|file|commit|branch)\b", q))
    return has_recency and has_context


def _question_wants_main_branch(question: str) -> bool:
    q = (question or "").lower()
    return ("main branch" in q) or bool(re.search(r"\bon\s+main\b", q))


def _build_latest_snapshot_summary(snapshot: dict, wants_main: bool) -> str:
    ts = _format_snapshot_timestamp_with_timezone(snapshot.get("timestamp"))
    file_path = snapshot.get("active_file") or "an unknown file"
    branch = snapshot.get("git_branch") or "unknown"
    work_context = _extract_work_context(snapshot)
    scope = "Most recent main-branch snapshot:" if wants_main else "Most recent snapshot:"
    return "\n".join(
        [
            scope,
            f"- Work context: {work_context}",
            f"- File: {file_path}",
            f"- Branch: {branch}",
            f"- Time: {ts}",
        ]
    )


def _extract_work_context(snapshot: dict) -> str:
    for key in ("summary", "shadow_graph", "document"):
        value = str(snapshot.get(key) or "").strip()
        if value:
            normalized = " ".join(value.split())
            return normalized[:180]
    return "No work context available."


def _format_snapshot_timestamp_with_timezone(raw_timestamp: Any) -> str:
    if raw_timestamp is None:
        return "unknown time"

    dt: datetime | None = None

    if isinstance(raw_timestamp, (int, float)):
        ts = float(raw_timestamp)
        if ts > 1_000_000_000_000:
            ts /= 1000.0
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    elif isinstance(raw_timestamp, str):
        value = raw_timestamp.strip()
        if not value:
            return "unknown time"
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(value)
        except Exception:
            return str(raw_timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    else:
        return str(raw_timestamp)

    tz_name = dt.tzname() or "UTC"
    tz_offset = dt.strftime("%z")
    if len(tz_offset) == 5:
        tz_offset = f"{tz_offset[:3]}:{tz_offset[3:]}"
    elif not tz_offset:
        tz_offset = "+00:00"

    return f"{dt.isoformat()} ({tz_name} {tz_offset})"


def _get_timestamp_float(snapshot: dict | None) -> float:
    """Convert snapshot timestamp to float (unix timestamp) for comparison."""
    if not snapshot:
        return 0.0
    
    ts = snapshot.get("timestamp")
    if isinstance(ts, (int, float)):
        return float(ts)
    
    if isinstance(ts, str):
        try:
            # Try ISO format first
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            return 0.0
    
    return 0.0


def _pick_newer_snapshot(a: dict | None, b: dict | None) -> dict | None:
    """Return the snapshot with the more recent timestamp."""
    if a is None:
        return b
    if b is None:
        return a
    
    ta = _get_timestamp_float(a)
    tb = _get_timestamp_float(b)
    return a if ta >= tb else b


def _parse_terminal_commands(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        try:
            import json
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except Exception:
            return []
    return []


def _is_snapshot_id(target: str) -> bool:
    return bool(re.match(r"^[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$", target.strip().lower()))


def _parse_snapshot_terminal_commands(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except Exception:
            return []
    return []


def _deduplicate_snapshots(snapshots: list[dict]) -> list[dict]:
    seen_ids: set[str] = set()
    deduped: list[dict] = []

    for snapshot in snapshots:
        snapshot_id = str(snapshot.get("id") or "")
        dedupe_key = snapshot_id or f"{snapshot.get('timestamp')}::{snapshot.get('active_file')}"
        if dedupe_key in seen_ids:
            continue
        seen_ids.add(dedupe_key)
        deduped.append(snapshot)

    deduped.sort(key=lambda s: str(s.get("timestamp") or ""))
    return deduped


def _extract_relevant_commands(snapshots: list[dict]) -> list[str]:
    commands: list[str] = []
    for snapshot in snapshots:
        for cmd in _parse_snapshot_terminal_commands(snapshot.get("terminal_commands"))[-3:]:
            if cmd not in commands:
                commands.append(cmd)
    return commands[:6]


async def _synthesize_decision_history(
    symbol_name: str,
    commit_message: str,
    snapshots: list[dict],
) -> tuple[str, list[str], list[str], float]:
    snapshot_context = "\n\n".join([
        (
            f"[{s.get('timestamp', 'unknown')}] Branch: {s.get('git_branch') or 'unknown'}\n"
            f"Active file: {s.get('active_file') or 'unknown'}\n"
            f"Terminal: {_parse_snapshot_terminal_commands(s.get('terminal_commands'))[-3:] or 'none'}\n"
            f"Summary: {s.get('summary') or 'No summary'}"
        )
        for s in snapshots
    ])

    prompt = f"""
A developer is hovering over the function `{symbol_name}` in their editor.
The commit that last changed this function has the message: "{commit_message}"

Based on the workspace snapshots captured around the time of this change,
reconstruct the decision history. Be concise — this is a tooltip, not an essay.

Answer these questions in ≤4 sentences total:
1. Why was this function written this way? (1 sentence)
2. What was tried before and why it didn't work? (1-2 sentences, only if evidence exists)
3. What key terminal commands or context led to this approach? (1 sentence, only if relevant)

If there's not enough context, say "No workspace history found for this change."
Do not hallucinate. Only state what the snapshots support.

Workspace snapshots:
{snapshot_context}
"""

    # Keep synthesis bounded to avoid API gateway timeouts during hover requests.
    response = await asyncio.wait_for(
        archaeology_async_llm_client.chat.completions.create(
            model=get_chat_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.2,
        ),
        timeout=12,
    )

    summary = (response.choices[0].message.content or "").strip() or "No workspace history found for this change."

    newest_branch = snapshots[-1].get("git_branch") if snapshots else None
    branches_tried = list(dict.fromkeys([
        str(s.get("git_branch"))
        for s in snapshots
        if s.get("git_branch") and s.get("git_branch") != newest_branch
    ]))[:3]

    terminal_commands = _extract_relevant_commands(snapshots)
    confidence = min(len(snapshots) / 5.0, 1.0)
    return summary, branches_tried, terminal_commands, confidence


def _build_fallback_decision_summary(symbol_name: str, commit_message: str, snapshots: list[dict]) -> str:
    if not snapshots:
        return "No workspace history found for this change."

    newest = snapshots[-1]
    oldest = snapshots[0]
    newest_file = newest.get("active_file") or "unknown file"
    newest_branch = newest.get("git_branch") or "unknown"
    time_span = f"{oldest.get('timestamp', 'unknown')} → {newest.get('timestamp', 'unknown')}"

    lines = [
        f"Found {len(snapshots)} snapshot(s) for `{symbol_name}` around commit '{commit_message[:80]}'.",
        f"Latest context shows edits in {newest_file} on branch {newest_branch}.",
        f"Observed snapshot window: {time_span}.",
    ]

    commands = _extract_relevant_commands(snapshots)
    if commands:
        lines.append(f"Recent terminal context includes: {', '.join(commands[:3])}.")

    return " ".join(lines)


def _is_safe_resurrection_command(command: str) -> bool:
    normalized = (command or "").strip().lower()
    if not normalized:
        return False
    blocked_prefixes = (
        "rm ", "del ", "rmdir ", "format ", "shutdown ", "reboot ",
        "git reset --hard", "git clean -fd", "dropdb ", "sudo ", "powershell -c",
    )
    if normalized.startswith(blocked_prefixes):
        return False
    allowed_prefixes = (
        "npm ", "pnpm ", "yarn ", "python ", "pytest ", "uvicorn ", "poetry ",
        "pip ", "make ", "cargo ", "go ", "dotnet ",
    )
    return normalized.startswith(allowed_prefixes)


def _workspaces_match(current_workspace: str | None, target_workspace: str | None) -> bool:
    if not current_workspace or not target_workspace:
        return False
    left = os.path.normcase(os.path.abspath(current_workspace))
    right = os.path.normcase(os.path.abspath(target_workspace))
    return left == right


async def _resolve_resurrection_snapshot(target: str, user_id: str) -> dict | None:
    normalized_target = (target or "").strip()
    if not normalized_target:
        return None

    if _is_snapshot_id(normalized_target):
        by_id = await vector_db.get_snapshot_by_id(snapshot_id=normalized_target, user_id=user_id)
        if by_id:
            return by_id

    timeline = await vector_db.get_snapshot_timeline(limit=1000, user_id=user_id)
    if not timeline:
        return None

    target_lower = normalized_target.lower()

    branch_matches = [
        s for s in timeline
        if str(s.get("git_branch", "")).strip().lower() == target_lower
    ]
    if branch_matches:
        return branch_matches[-1]

    path_or_summary_matches = [
        s for s in timeline
        if target_lower in str(s.get("active_file", "")).lower()
        or target_lower in str(s.get("summary", "")).lower()
    ]
    if path_or_summary_matches:
        return path_or_summary_matches[-1]

    return None


def _build_resurrection_plan(snapshot: dict, target: str, current_workspace: str | None) -> tuple[list[ResurrectionCommand], str, SafetyReport]:
    commands: list[ResurrectionCommand] = []

    workspace_dir = str(snapshot.get("workspace_folder") or "").strip() or None
    active_file = str(snapshot.get("active_file") or "").strip() or None
    branch = str(snapshot.get("git_branch") or "").strip() or None
    timestamp = str(snapshot.get("timestamp") or "unknown time")
    summary = str(snapshot.get("summary") or "No summary available.")

    should_open_workspace = bool(workspace_dir and not _workspaces_match(current_workspace, workspace_dir))
    if should_open_workspace and workspace_dir:
        commands.append(ResurrectionCommand(type="open_workspace", filePath=workspace_dir))

    commands.append(ResurrectionCommand(type="git_stash"))
    if branch:
        commands.append(ResurrectionCommand(type="git_checkout", branch=branch))

    if active_file:
        commands.append(ResurrectionCommand(type="open_file", filePath=active_file, viewColumn=1))

    terminal_commands = _parse_terminal_commands(snapshot.get("terminal_commands"))
    last_safe_terminal_command = next((cmd for cmd in reversed(terminal_commands) if _is_safe_resurrection_command(cmd)), None)
    if last_safe_terminal_command:
        commands.append(ResurrectionCommand(type="split_terminal", command=last_safe_terminal_command))

    plan_summary = (
        f"Resolved target '{target}' to snapshot at {timestamp}. "
        f"Will stash local changes, checkout branch {branch or 'current'}, "
        f"open {active_file or 'the captured file'}, and restore a safe terminal command. "
        f"Snapshot summary: {summary}"
    )

    estimated_risk = "medium" if branch or should_open_workspace else "low"
    impact = SafetyReport(
        conflicts=[],
        unstashed_changes=True,
        estimated_risk=estimated_risk,
    )
    return commands, plan_summary, impact




# ── Redirects ───────────────────────────────────────────────────

@app.get("/signup")
@app.post("/signup")
async def signup_redirect():
    """Redirect to the correct auth endpoint."""
    return {"detail": "Please use /api/v1/auth/signup for sign up requests."}


@app.get("/login")
@app.post("/login")
async def login_redirect():
    """Redirect to the correct auth endpoint."""
    return {"detail": "Please use /api/v1/auth/login for login requests."}


# ── Endpoints ───────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Simple health check for load balancers and monitoring."""
    return {"status": "ok", "service": "secondcortex-backend", "version": "0.3.0"}


@app.get("/api/sync/auth")
async def get_sync_auth(user_id: str = Depends(get_current_user)):
    """Issue a short-lived PowerSync-compatible token for the authenticated user."""
    user = user_db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Unknown user")

    checkpoint = user_db.get_sync_checkpoint(user_id)
    sync_token = _create_sync_token(user_id=user_id, team_id=user.get("team_id"))
    return {
        "token": sync_token,
        "user_id": user_id,
        "team_id": user.get("team_id"),
        "checkpoint": checkpoint,
    }


@app.put("/api/sync/data")
async def put_sync_data(
    body: SyncDataRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
):
    """
    Receive synced snapshot rows from extension local SQLite queue.
    Stores raw rows, then triggers existing retriever/vector pipeline.
    """
    sync_token = request.headers.get("X-Sync-Token")
    if not _verify_sync_token(sync_token, user_id):
        raise HTTPException(status_code=401, detail="Invalid sync token")

    user = user_db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Unknown user")

    synced_ids: list[str] = []
    team_id = user.get("team_id")

    for row in body.rows:
        if row.user_id != user_id:
            logger.warning("Skipping sync row with mismatched user_id row=%s auth=%s", row.user_id, user_id)
            continue

        raw_row = {
            "id": row.id,
            "user_id": user_id,
            "team_id": team_id,
            "workspace": row.workspace,
            "active_file": row.active_file,
            "git_branch": row.git_branch,
            "terminal_commands": row.terminal_commands,
            "summary": row.summary,
            "enriched_context": row.enriched_context,
            "timestamp": row.timestamp,
            "synced": 1,
        }
        user_db.upsert_synced_snapshot(raw_row)

        payload = _snapshot_payload_from_sync_row(row)
        background_tasks.add_task(retriever.process_snapshot, payload, user_id)

        _latest_ingested_snapshot[user_id] = {
            "id": row.id,
            "timestamp": datetime.utcfromtimestamp(max(0, row.timestamp) / 1000).isoformat() + "Z",
            "active_file": row.active_file,
            "git_branch": row.git_branch,
            "summary": row.summary or f"Capture received: editing {row.active_file}",
        }
        synced_ids.append(row.id)

    checkpoint = user_db.get_sync_checkpoint(user_id)
    return {"status": "ok", "synced_ids": synced_ids, "checkpoint": checkpoint}


@app.get("/api/sync/checkpoint")
async def get_sync_checkpoint(user_id: str = Depends(get_current_user)):
    """Return current checkpoint for authenticated user's team scope."""
    checkpoint = user_db.get_sync_checkpoint(user_id)
    return {"checkpoint": checkpoint}


@app.get("/api/sync/watch")
async def watch_team_snapshots(token: str, after: int = 0):
    """Server-sent events stream used by frontend watched queries (no polling)."""

    payload = verify_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = str(payload.get("sub"))

    async def event_stream():
        last_checkpoint = after
        while True:
            snapshots = user_db.get_team_snapshots(user_id=user_id, per_member_limit=500)
            checkpoint = max([int(s.get("timestamp") or 0) for s in snapshots], default=0)

            if checkpoint > last_checkpoint:
                team_payload: list[dict] = []
                for snapshot in snapshots:
                    owner = user_db.get_user_by_id(str(snapshot.get("user_id") or "")) or {}
                    team_payload.append({
                        "id": snapshot.get("id"),
                        "user_id": snapshot.get("user_id"),
                        "developer_name": owner.get("display_name") or owner.get("email") or snapshot.get("user_id"),
                        "active_file": snapshot.get("active_file"),
                        "git_branch": snapshot.get("git_branch"),
                        "summary": snapshot.get("summary"),
                        "timestamp": int(snapshot.get("timestamp") or 0),
                    })

                body = json.dumps({"checkpoint": checkpoint, "rows": team_payload})
                yield f"event: team_snapshots\ndata: {body}\n\n"
                last_checkpoint = checkpoint

            await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/v1/snapshot", status_code=200)
async def receive_snapshot(
    payload: SnapshotPayload,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
):
    """
    Receive a sanitized IDE snapshot from the VS Code extension.
    Returns 200 OK instantly, then processes asynchronously via Retriever.
    """
    logger.info("Received snapshot for file: %s (user=%s)", payload.active_file, user_id)

    # Immediate cache update so latest queries can reflect ingest instantly,
    # even if async retrieval/vector indexing is still in progress.
    _latest_ingested_snapshot[user_id] = {
        "id": "pending",
        "timestamp": payload.timestamp.isoformat() if hasattr(payload.timestamp, "isoformat") else str(payload.timestamp),
        "active_file": payload.active_file,
        "git_branch": payload.git_branch,
        "summary": f"Capture received: editing {payload.active_file}",
    }

    background_tasks.add_task(retriever.process_snapshot, payload, user_id)
    return {"status": "accepted", "message": "Snapshot queued for processing."}


@app.post("/api/v1/ingest/git", response_model=RetroIngestResponse)
async def ingest_git_history(
    request: RetroIngestRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Retroactively ingest existing git history into user memory.
    Includes commit messages/diffs/code comments and, when available, GitHub PR context.
    """
    logger.info(
        "Retro ingest requested (user=%s, repo=%s, commits=%s, prs=%s)",
        user_id,
        request.repo_path,
        request.max_commits,
        request.max_pull_requests,
    )

    try:
        records, summary = git_ingestion.mine(
            repo_path=request.repo_path,
            max_commits=request.max_commits,
            max_pull_requests=request.max_pull_requests,
            include_pull_requests=request.include_pull_requests,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Git ingest failed: {exc}")

    ingested_count = 0
    for record in records:
        metadata = MemoryMetadata(
            operation=MemoryOperation.ADD,
            entities=[record.active_file, record.git_branch],
            relations=[],
            summary=record.summary,
        )

        stored = StoredSnapshot(
            id=record.id,
            timestamp=record.timestamp,
            workspace_folder=record.workspace_folder,
            active_file=record.active_file,
            language_id=record.language_id,
            shadow_graph=record.shadow_graph,
            git_branch=record.git_branch,
            terminal_commands=record.terminal_commands,
            metadata=metadata,
        )
        stored.embedding = await vector_db.generate_embedding(
            f"{record.summary}\n{record.shadow_graph[:4000]}"
        )
        await vector_db.upsert_snapshot(stored, user_id=user_id)
        ingested_count += 1

    return RetroIngestResponse(
        status="ok",
        repo=summary.repo,
        branch=summary.branch,
        ingestedCount=ingested_count,
        commitCount=summary.commit_count,
        prCount=summary.pr_count,
        commentCount=summary.comment_count,
        skippedCount=summary.skipped_count,
        warnings=summary.warnings,
    )


@app.get("/api/v1/events")
async def get_events(user_id: str = Depends(get_current_user)):
    """
    Endpoint for the Next.js React Flow to poll recent snapshots.
    Scoped to the authenticated user's collection.
    """
    results = await vector_db.get_recent_snapshots(limit=10, user_id=user_id)

    events = []
    for r in results:
        events.append({
            "id": r.get("id"),
            "timestamp": r.get("timestamp"),
            "active_file": r.get("active_file"),
            "git_branch": r.get("git_branch"),
            "summary": r.get("summary"),
            "entities": r.get("entities", "").split(",") if r.get("entities") else [],
            "relations": []
        })

    return {"events": events}


@app.get("/api/v1/snapshots/timeline")
async def get_snapshot_timeline(
    limit: int = 200,
    user_id: str = Depends(get_current_user),
):
    """Timeline feed for Shadow Graph time-travel (oldest -> newest)."""
    capped_limit = max(1, min(limit, 1000))
    results = await vector_db.get_snapshot_timeline(limit=capped_limit, user_id=user_id)

    timeline = []
    for r in results:
        timeline.append({
            "id": r.get("id"),
            "timestamp": r.get("timestamp"),
            "active_file": r.get("active_file"),
            "git_branch": r.get("git_branch"),
            "summary": r.get("summary"),
            "entities": r.get("entities", "").split(",") if r.get("entities") else [],
        })

    return {"timeline": timeline}


@app.get("/api/v1/snapshots/{snapshot_id}")
async def get_snapshot_by_id(
    snapshot_id: str,
    user_id: str = Depends(get_current_user),
):
    """Detailed metadata lookup for a single snapshot, used by VS Code preview."""
    snapshot = await vector_db.get_snapshot_by_id(snapshot_id=snapshot_id, user_id=user_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return {
        "snapshot": {
            "id": snapshot.get("id"),
            "timestamp": snapshot.get("timestamp"),
            "workspace_folder": snapshot.get("workspace_folder"),
            "active_file": snapshot.get("active_file"),
            "git_branch": snapshot.get("git_branch"),
            "summary": snapshot.get("summary"),
            "entities": snapshot.get("entities", "").split(",") if snapshot.get("entities") else [],
            "shadow_graph": snapshot.get("document") or snapshot.get("shadow_graph") or "",
        }
    }



@app.get("/api/v1/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    session_id: str | None = None,
    user_id: str = Depends(get_current_user)
):
    """Retrieve chat history for the current user, optionally filtered by session."""
    history = user_db.get_chat_history(user_id, session_id=session_id)
    return {"messages": history}


@app.get("/api/v1/chat/sessions", response_model=schemas.ChatSessionsResponse)
async def get_chat_sessions(
    user_id: str = Depends(get_current_user)
):
    """List all unique chat sessions for the current user."""
    sessions = user_db.get_chat_sessions(user_id)
    return {"sessions": sessions}


@app.delete("/api/v1/chat/history")
async def clear_chat_history(
    session_id: str | None = None,
    user_id: str = Depends(get_current_user)
):
    """Clear chat history (single session or all)."""
    user_db.delete_chat_history(user_id, session_id=session_id)
    return {"message": "History cleared"}


@app.post("/api/v1/chat/sessions")
async def create_chat_session(
    req: dict = Body(...),
    user_id: str = Depends(get_current_user)
):
    """Create a new chat session for the current user."""
    session_id = user_db.create_chat_session(user_id, title=req.get("title", "New Chat"))
    return {"session_id": session_id}


@app.post("/api/v1/query", response_model=QueryResponse)
async def handle_query(
    req: QueryRequest,
    session_id: str | None = None,
    user_id: str = Depends(get_current_user)
):
    """
    Main entry point for SecondCortex queries.
    Combines retrieval, planning, and execution logic.
    """
    try:
        logger.info("Query received: %s (user=%s, session=%s)", req.question, user_id, session_id)

        # Deterministic fast-path for recency questions.
        # Avoids LLM choosing semantically similar but older snapshots.
        if _is_latest_snapshot_question(req.question):
            wants_main = _question_wants_main_branch(req.question)
            timeline = await vector_db.get_snapshot_timeline(limit=50, user_id=user_id)
            recent = list(reversed(timeline))
            latest_ingested = _latest_ingested_snapshot.get(user_id)

            if wants_main:
                recent = [r for r in recent if str(r.get("git_branch", "")).strip().lower() == "main"]
                if latest_ingested and str(latest_ingested.get("git_branch", "")).strip().lower() != "main":
                    latest_ingested = None

            latest_stored = recent[0] if recent else None
            latest = _pick_newer_snapshot(latest_ingested, latest_stored)

            if latest:
                response = QueryResponse(
                    summary=_build_latest_snapshot_summary(latest, wants_main),
                    reasoningLog=[
                        "Detected latest-snapshot query and used recency retrieval.",
                        f"Selected snapshot id={latest.get('id', 'unknown')} timestamp={latest.get('timestamp', 'unknown')}",
                    ],
                    commands=[],
                )
            else:
                response = QueryResponse(
                    summary=(
                        "No matching snapshots were found for that latest query. "
                        "Try again after a new snapshot is captured."
                    ),
                    reasoningLog=["Recency retrieval returned no snapshots."],
                    commands=[],
                )

            user_db.save_chat_message(user_id, "user", req.question, session_id=session_id)
            user_db.save_chat_message(user_id, "assistant", response.summary, session_id=session_id)
            return response

        # Step 1: Plan — break the question into search tasks
        plan_result = await planner.plan(req.question, user_id=user_id)

        # Step 2: Execute — synthesize and validate
        response = await executor.synthesize(req.question, plan_result)

        # Step 3: Persist history
        user_db.save_chat_message(user_id, "user", req.question, session_id=session_id)
        user_db.save_chat_message(user_id, "assistant", response.summary, session_id=session_id)

        logger.info("Query answered: %s", response.summary[:100])
        return response
    except Exception as exc:
        import traceback
        err = traceback.format_exc()
        exc_str = str(exc)

        # Handle Gemini 429 rate limit errors gracefully
        if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
            logger.warning("QUERY RATE LIMITED: %s", exc_str[:200])
            raise HTTPException(
                status_code=429,
                detail="Rate limit reached. The Gemini API free tier quota has been exhausted. Please wait a minute and try again."
            )

        logger.error("QUERY PIPELINE CRASH: %s\n%s", exc, err)
        raise HTTPException(status_code=500, detail=f"Query pipeline error: {str(exc)}")



@app.post("/api/v1/resurrect", response_model=ResurrectionResponse)
async def handle_resurrection(
    request: ResurrectionRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Generate a Workspace Resurrection plan for a given target branch/snapshot.
    """
    logger.info("Resurrection requested for target: %s (user=%s)", request.target, user_id)

    snapshot = await _resolve_resurrection_snapshot(request.target, user_id)
    if not snapshot:
        raise HTTPException(
            status_code=404,
            detail=(
                "No matching snapshot found for that target. "
                "Try a valid branch name, file hint, or exact snapshot ID from Shadow Graph."
            ),
        )

    commands, plan_summary, impact = _build_resurrection_plan(
        snapshot=snapshot,
        target=request.target,
        current_workspace=request.current_workspace,
    )

    return ResurrectionResponse(
        commands=commands,
        impact_analysis=impact,
        planSummary=plan_summary,
    )


@app.post("/api/v1/decision-archaeology", response_model=ArchaeologyResponse)
async def decision_archaeology(
    request: ArchaeologyRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Given function + file + commit context, reconstruct decision history
    from stored workspace snapshots and synthesize a hover-friendly summary.
    """
    logger.info(
        "Decision archaeology request: %s in %s (user=%s)",
        request.symbol_name,
        request.file_path,
        user_id,
    )

    query = (
        f"File: {request.file_path}\n"
        f"Function: {request.symbol_name}\n"
        f"Signature: {request.signature}\n"
        f"Commit: {request.commit_hash}\n"
        f"Commit message: {request.commit_message}\n"
        f"Author: {request.author}\n"
        f"Timestamp: {request.timestamp.isoformat()}"
    )

    time_window_start = request.timestamp - timedelta(hours=2)
    time_window_end = request.timestamp + timedelta(hours=1)

    # Bound expensive retrieval to keep hover interactions responsive.
    timeline_task = asyncio.create_task(vector_db.get_snapshot_timeline(limit=800, user_id=user_id))
    semantic_task = asyncio.create_task(vector_db.semantic_search(query=query, top_k=6, user_id=user_id))
    symbol_task = asyncio.create_task(
        vector_db.semantic_search(
            query=f"function {request.symbol_name} implementation decision {request.commit_hash}",
            top_k=4,
            user_id=user_id,
        )
    )

    timeline, semantic_results, symbol_results = await asyncio.gather(
        asyncio.wait_for(timeline_task, timeout=6),
        asyncio.wait_for(semantic_task, timeout=6),
        asyncio.wait_for(symbol_task, timeout=6),
        return_exceptions=True,
    )

    if isinstance(timeline, Exception):
        logger.warning("Decision archaeology timeline retrieval degraded: %s", timeline)
        timeline = []
    if isinstance(semantic_results, Exception):
        logger.warning("Decision archaeology semantic retrieval degraded: %s", semantic_results)
        semantic_results = []
    if isinstance(symbol_results, Exception):
        logger.warning("Decision archaeology symbol retrieval degraded: %s", symbol_results)
        symbol_results = []

    time_filtered: list[dict] = []
    for snapshot in timeline:
        if str(snapshot.get("active_file") or "") != request.file_path:
            continue

        snapshot_ts = _parse_iso_timestamp(str(snapshot.get("timestamp") or ""))
        if snapshot_ts is None:
            continue

        if time_window_start <= snapshot_ts <= time_window_end:
            time_filtered.append(snapshot)

    semantic_file_filtered = [
        s for s in semantic_results
        if str(s.get("active_file") or "") == request.file_path
    ]
    symbol_file_filtered = [
        s for s in symbol_results
        if str(s.get("active_file") or "") == request.file_path
    ]

    all_results = _deduplicate_snapshots(
        time_filtered + semantic_file_filtered + symbol_file_filtered
    )

    # Keep synthesis context compact for predictable latency.
    all_results = all_results[-18:]

    if not all_results:
        return ArchaeologyResponse(found=False, summary=None)

    try:
        summary, branches_tried, terminal_commands, confidence = await asyncio.wait_for(
            _synthesize_decision_history(
            symbol_name=request.symbol_name,
            commit_message=request.commit_message,
            snapshots=all_results,
            ),
            timeout=14,
        )
    except asyncio.TimeoutError:
        logger.warning("Decision synthesis timed out for %s in %s", request.symbol_name, request.file_path)
        return ArchaeologyResponse(
            found=True,
            summary=_build_fallback_decision_summary(request.symbol_name, request.commit_message, all_results),
            branchesTried=list(dict.fromkeys([str(s.get("git_branch")) for s in all_results if s.get("git_branch")]))[:3],
            terminalCommands=_extract_relevant_commands(all_results),
            confidence=min(len(all_results) / 8.0, 0.6),
        )
    except Exception as exc:
        logger.error("Decision synthesis failed: %s", exc)
        return ArchaeologyResponse(
            found=True,
            summary=_build_fallback_decision_summary(request.symbol_name, request.commit_message, all_results),
            branchesTried=list(dict.fromkeys([str(s.get("git_branch")) for s in all_results if s.get("git_branch")]))[:3],
            terminalCommands=_extract_relevant_commands(all_results),
            confidence=min(len(all_results) / 10.0, 0.5),
        )

    return ArchaeologyResponse(
        found=True,
        summary=summary,
        branchesTried=branches_tried,
        terminalCommands=terminal_commands,
        confidence=confidence,
    )


# ── Run server ──────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info",
    )
