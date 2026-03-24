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
import traceback
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agents.executor import ExecutorAgent
from agents.planner import PlannerAgent
from agents.retriever import RetrieverAgent
from agents.simulator import SimulatorAgent
from auth.jwt_handler import get_current_principal, get_current_user
from auth.routes import router as auth_router
from projects.routes import router as projects_router, project_db
from teams.routes import router as teams_router
from teams.summary_routes import router as summary_router
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
)
from auth.routes import user_db
from services.vector_db import VectorDBService
from services.llm_client import task_chat_completion, validate_llm_configuration
from services.git_ingest import RetroGitIngestionService

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


@app.on_event("startup")
async def validate_startup_llm_config() -> None:
    errors = validate_llm_configuration()
    if errors:
        message = " | ".join(errors)
        logger.error("LLM startup validation failed: %s", message)
        raise RuntimeError(f"Invalid LLM configuration: {message}")
    logger.info("LLM startup validation passed.")


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
app.include_router(projects_router)
app.include_router(teams_router)
app.include_router(summary_router)

# ── MCP Server Mount ──────────────────────────
from mcp_server import mcp

app.mount("/mcp", mcp.sse_app())

# ── Service & Agent Initialization ──────────────────────────────
vector_db = VectorDBService()
retriever = RetrieverAgent(vector_db)
planner = PlannerAgent(vector_db)
executor = ExecutorAgent()
simulator = SimulatorAgent()
git_ingestion = RetroGitIngestionService()


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


def _normalize_code_path(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    normalized = raw.replace("\\", "/")
    normalized = re.sub(r"/+", "/", normalized)
    return normalized.lower()


def _to_utc_aware_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_iso_timestamp(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None

    return _to_utc_aware_timestamp(parsed)


def _paths_match(snapshot_path: str | None, requested_path: str | None) -> bool:
    left = _normalize_code_path(snapshot_path)
    right = _normalize_code_path(requested_path)

    if not left or not right:
        return False
    if left == right:
        return True
    if left.endswith(f"/{right}") or right.endswith(f"/{left}"):
        return True

    return os.path.basename(left) == os.path.basename(right)


def _snapshot_mentions_symbol(snapshot: dict, symbol_name: str) -> bool:
    needle = (symbol_name or "").strip().lower()
    if not needle:
        return False

    summary = str(snapshot.get("summary") or "").lower()
    if needle in summary:
        return True

    active_symbol = str(snapshot.get("active_symbol") or "").lower()
    if needle in active_symbol:
        return True

    signatures_raw = snapshot.get("function_signatures")
    if isinstance(signatures_raw, str) and signatures_raw.strip():
        try:
            parsed_signatures = json.loads(signatures_raw)
            if isinstance(parsed_signatures, list) and any(needle in str(sig).lower() for sig in parsed_signatures):
                return True
        except Exception:
            if needle in signatures_raw.lower():
                return True
    elif isinstance(signatures_raw, list) and any(needle in str(sig).lower() for sig in signatures_raw):
        return True

    shadow_graph = str(snapshot.get("shadow_graph") or snapshot.get("document") or "").lower()
    if needle in shadow_graph:
        return True

    entities_raw = snapshot.get("entities")
    if isinstance(entities_raw, list):
        return any(needle in str(entity).lower() for entity in entities_raw)
    if isinstance(entities_raw, str):
        return needle in entities_raw.lower()

    return False


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
        task_chat_completion(
            task="archaeology",
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


def _principal_scopes(principal: dict) -> set[str]:
    scopes = principal.get("scopes") or []
    if isinstance(scopes, str):
        scopes = [scopes]
    return {str(scope) for scope in scopes}


def _require_project_access(user_id: str, project_id: str | None) -> None:
    if not project_id:
        return

    user = user_db.get_user_by_id(user_id)
    team_id = user.get("team_id") if user else None
    if not project_db.user_can_access_project(user_id=user_id, team_id=team_id, project_id=project_id):
        raise HTTPException(status_code=403, detail="Not authorized to access this project")


def _require_pm_guest_project_access(principal: dict, project_id: str | None) -> None:
    if not project_id:
        return

    role = str(principal.get("role") or "user")
    if role != "pm_guest":
        return

    scopes = _principal_scopes(principal)
    if "pm:read" not in scopes:
        raise HTTPException(status_code=403, detail="PM guest token lacks read scope.")

    team_id = str(principal.get("team_id") or "").strip()
    if not team_id:
        raise HTTPException(status_code=403, detail="PM guest token missing team scope.")

    project = project_db.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if str(project.get("team_id") or "").strip() != team_id or str(project.get("visibility") or "") != "team":
        raise HTTPException(status_code=403, detail="Not authorized to access this project")


def _resolve_timeline_user_ids(principal: dict) -> list[str]:
    role = str(principal.get("role") or "user")
    if role != "pm_guest":
        user_id = str(principal.get("sub") or "").strip()
        return [user_id] if user_id else []

    if "pm:read" not in _principal_scopes(principal):
        raise HTTPException(status_code=403, detail="PM guest token lacks read scope.")

    team_id = str(principal.get("team_id") or "").strip()
    if not team_id:
        raise HTTPException(status_code=403, detail="PM guest token missing team scope.")

    members = user_db.get_team_members(team_id)
    return [str(member.get("id") or "").strip() for member in members if str(member.get("id") or "").strip()]


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
    if settings.project_scoped_ingestion_enabled and not payload.project_id:
        raise HTTPException(status_code=400, detail="projectId is required when project scoped ingestion is enabled")

    logger.info("Received snapshot for file: %s (user=%s)", payload.active_file, user_id)

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

    concurrency_limit = min(8, max(1, len(records)))
    semaphore = asyncio.Semaphore(concurrency_limit)

    async def _ingest_record(record: StoredSnapshot) -> bool:
        async with semaphore:
            try:
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
                return True
            except Exception as exc:
                summary.warnings.append(f"Failed to ingest record {record.id}: {exc}")
                logger.warning("Retro ingest record failed (id=%s, user=%s): %s", record.id, user_id, exc)
                return False

    ingestion_results = await asyncio.gather(*[_ingest_record(record) for record in records])
    ingested_count = sum(1 for ok in ingestion_results if ok)

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
async def get_events(
    projectId: str | None = None,
    user_id: str = Depends(get_current_user),
):
    """
    Endpoint for the Next.js React Flow to poll recent snapshots.
    Scoped to the authenticated user's collection.
    """
    _require_project_access(user_id=user_id, project_id=projectId)
    results = await vector_db.get_recent_snapshots(limit=10, user_id=user_id, project_id=projectId)

    events = []
    for r in results:
        events.append({
            "id": r.get("id"),
            "timestamp": r.get("timestamp"),
            "active_file": r.get("active_file"),
            "git_branch": r.get("git_branch"),
            "project_id": r.get("project_id") or None,
            "summary": r.get("summary"),
            "entities": r.get("entities", "").split(",") if r.get("entities") else [],
            "relations": []
        })

    return {"events": events}


@app.get("/api/v1/snapshots/timeline")
async def get_snapshot_timeline(
    limit: int = 200,
    projectId: str | None = None,
    principal: dict = Depends(get_current_principal),
):
    """Timeline feed for Shadow Graph time-travel (oldest -> newest)."""
    role = str(principal.get("role") or "user")
    if role == "pm_guest":
        _require_pm_guest_project_access(principal=principal, project_id=projectId)
    else:
        user_id = str(principal.get("sub") or "")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload.")
        _require_project_access(user_id=user_id, project_id=projectId)

    capped_limit = max(1, min(limit, 1000))

    user_ids = _resolve_timeline_user_ids(principal)
    if not user_ids:
        return {"timeline": []}

    if len(user_ids) == 1:
        results = await vector_db.get_snapshot_timeline(limit=capped_limit, user_id=user_ids[0], project_id=projectId)
    else:
        merged_results: list[dict] = []
        for member_user_id in user_ids:
            member_timeline = await vector_db.get_snapshot_timeline(
                limit=capped_limit,
                user_id=member_user_id,
                project_id=projectId,
            )
            for row in member_timeline:
                enriched = dict(row)
                enriched["user_id"] = member_user_id
                merged_results.append(enriched)

        merged_results.sort(
            key=lambda row: vector_db._timestamp_sort_key(row.get("timestamp")),
            reverse=True,
        )
        results = merged_results[:capped_limit]

    timeline = []
    for r in results:
        timeline.append({
            "id": r.get("id"),
            "user_id": r.get("user_id"),
            "timestamp": r.get("timestamp"),
            "active_file": r.get("active_file"),
            "git_branch": r.get("git_branch"),
            "project_id": r.get("project_id") or None,
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
    _require_project_access(user_id=user_id, project_id=snapshot.get("project_id") or None)

    return {
        "snapshot": {
            "id": snapshot.get("id"),
            "timestamp": snapshot.get("timestamp"),
            "workspace_folder": snapshot.get("workspace_folder"),
            "active_file": snapshot.get("active_file"),
            "git_branch": snapshot.get("git_branch"),
            "project_id": snapshot.get("project_id") or None,
            "summary": snapshot.get("summary"),
            "entities": snapshot.get("entities", "").split(",") if snapshot.get("entities") else [],
            "active_symbol": snapshot.get("active_symbol"),
            "function_signatures": _parse_snapshot_entities(snapshot.get("function_signatures")),
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

        # Step 1: Plan - break the question into search tasks
        plan_result = await planner.plan(req.question, user_id=user_id)

        # Step 2: Dual retrieval (facts + snapshots)
        facts = await vector_db.recall_facts(req.question, top_k=5, user_id=user_id, min_salience=0.3)
        retrieved_facts = [{"id": f.get("id"), "content": f.get("document"), "kind": f.get("kind"), "salience": f.get("salience")} for f in facts]
        retrieved_snapshots = [{"id": item.get("id"), "timestamp": item.get("timestamp"), "file": item.get("activeFile"), "branch": item.get("gitBranch")} for item in plan_result.retrieved_context[:5]]

        # Step 3: Execute — synthesize and validate
        response = await executor.synthesize(req.question, plan_result)

        # Step 4: Enrich response with retrieved facts and snapshots
        response.retrieved_facts = retrieved_facts
        response.retrieved_snapshots = retrieved_snapshots

        # Step 5: Persist history
        user_db.save_chat_message(user_id, "user", req.question, session_id=session_id)
        user_db.save_chat_message(user_id, "assistant", response.summary, session_id=session_id)

        logger.info("Query answered: %s", response.summary[:100])
        return response
    except Exception as exc:
        import traceback
        err = traceback.format_exc()
        exc_str = str(exc)

        # Handle provider rate limit errors gracefully
        if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
            logger.warning("QUERY RATE LIMITED: %s", exc_str[:200])
            raise HTTPException(
                status_code=429,
                detail="Rate limit reached for the configured LLM provider. Please wait a minute and try again."
            )

        logger.error("QUERY PIPELINE CRASH: %s\n%s", exc, err)
        raise HTTPException(status_code=500, detail=f"Query pipeline error: {str(exc)}")


@app.post("/api/v1/pm/query", response_model=QueryResponse)
async def handle_pm_query(
    req: QueryRequest,
    principal: dict = Depends(get_current_principal),
):
    """
    PM-safe query endpoint.
    Supports authenticated PM users and restricted PM guest sessions.
    """
    role = str(principal.get("role") or "user")
    user_id = str(principal.get("sub") or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload.")

    if role == "pm_guest" and "pm:chat" not in _principal_scopes(principal):
        raise HTTPException(status_code=403, detail="PM guest token lacks chat scope.")

    try:
        logger.info("PM query received: %s (user=%s)", req.question, user_id)

        plan_result = await planner.plan(req.question, user_id=user_id)
        response = await executor.synthesize(req.question, plan_result)

        # Restricted guest tokens should not persist into standard user chat history.
        if role != "pm_guest":
            user_db.save_chat_message(user_id, "user", req.question)
            user_db.save_chat_message(user_id, "assistant", response.summary)

        logger.info("PM query answered: %s", response.summary[:100])
        return response
    except Exception as exc:
        import traceback
        err = traceback.format_exc()
        exc_str = str(exc)

        if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
            logger.warning("PM QUERY RATE LIMITED: %s", exc_str[:200])
            raise HTTPException(
                status_code=429,
                detail="Rate limit reached for the configured LLM provider. Please wait a minute and try again."
            )

        logger.error("PM QUERY PIPELINE CRASH: %s\n%s", exc, err)
        raise HTTPException(status_code=500, detail=f"PM query pipeline error: {str(exc)}")


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
    _require_project_access(user_id=user_id, project_id=request.project_id)

    query = (
        f"File: {request.file_path}\n"
        f"Function: {request.symbol_name}\n"
        f"Signature: {request.signature}\n"
        f"Commit: {request.commit_hash}\n"
        f"Commit message: {request.commit_message}\n"
        f"Author: {request.author}\n"
        f"Timestamp: {request.timestamp.isoformat()}"
    )

    anchor_timestamp = _to_utc_aware_timestamp(request.timestamp)
    time_window_start = anchor_timestamp - timedelta(hours=2)
    time_window_end = anchor_timestamp + timedelta(hours=1)

    # Bound expensive retrieval to keep hover interactions responsive.
    timeline_task = asyncio.create_task(
        vector_db.get_snapshot_timeline(limit=800, user_id=user_id, project_id=request.project_id)
    )
    semantic_task = asyncio.create_task(
        vector_db.semantic_search(query=query, top_k=6, user_id=user_id, project_id=request.project_id)
    )
    symbol_task = asyncio.create_task(
        vector_db.semantic_search(
            query=f"function {request.symbol_name} implementation decision {request.commit_hash}",
            top_k=4,
            user_id=user_id,
            project_id=request.project_id,
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
        if request.project_id and str(snapshot.get("project_id") or "") != str(request.project_id):
            continue
        if not _paths_match(snapshot.get("active_file"), request.file_path):
            continue

        snapshot_ts = _parse_iso_timestamp(str(snapshot.get("timestamp") or ""))
        if snapshot_ts is None:
            continue

        if time_window_start <= snapshot_ts <= time_window_end:
            time_filtered.append(snapshot)

    semantic_file_filtered = [
        s for s in semantic_results
        if _paths_match(s.get("active_file"), request.file_path)
        and (not request.project_id or str(s.get("project_id") or "") == str(request.project_id))
    ]
    symbol_file_filtered = [
        s for s in symbol_results
        if _paths_match(s.get("active_file"), request.file_path)
        and (not request.project_id or str(s.get("project_id") or "") == str(request.project_id))
    ]

    all_results = _deduplicate_snapshots(
        time_filtered + semantic_file_filtered + symbol_file_filtered
    )

    if not all_results:
        symbol_candidates = [
            s
            for s in _deduplicate_snapshots(timeline + semantic_results + symbol_results)
            if _snapshot_mentions_symbol(s, request.symbol_name)
        ]
        all_results = symbol_candidates

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
