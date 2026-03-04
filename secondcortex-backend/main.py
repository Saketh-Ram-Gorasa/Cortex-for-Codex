"""
SecondCortex Backend — FastAPI Main Server

Endpoints:
  POST /api/v1/snapshot  — Receives sanitized IDE snapshots (returns 200 instantly,
                           processes in background via Retriever).
  POST /api/v1/query     — Receives a user question, runs Planner → Executor pipeline.
  POST /api/v1/resurrect — Receives a target branch/snapshot ID, returns resurrection commands.
  GET  /api/v1/events    — Polls recent snapshots for the Live Graph.
  GET  /health           — Health check.
"""

import logging
import sys
import os

# ── Force Python to see the local directories (fixes Azure ModuleNotFoundError) ──────────
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ── ChromaDB Compatibility Patch for Azure (Older SQLite3) ────────────────────────────────
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from agents.executor import ExecutorAgent
from agents.planner import PlannerAgent
from agents.retriever import RetrieverAgent
from config import settings
from models.schemas import (
    QueryRequest,
    QueryResponse,
    ResurrectionRequest,
    ResurrectionResponse,
    SnapshotPayload,
)
from services.vector_db import VectorDBService

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
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Service & Agent Initialization ──────────────────────────────
vector_db = VectorDBService()
retriever = RetrieverAgent(vector_db)
planner = PlannerAgent(vector_db)
executor = ExecutorAgent()

# ── Auth: Build the API key lookup table ────────────────────────
API_KEY_MAP = settings.get_api_key_map()
AUTH_ENABLED = len(API_KEY_MAP) > 0

if AUTH_ENABLED:
    logger.info("🔐 API key auth ENABLED — %d user(s) configured.", len(API_KEY_MAP))
else:
    logger.warning("⚠️  API key auth DISABLED — all requests allowed (set API_KEYS to enable).")


# ── Auth dependency ─────────────────────────────────────────────

async def get_current_user(x_api_key: str | None = Header(None)) -> str | None:
    """
    If auth is enabled, validates X-API-Key header and returns the user_id.
    If auth is disabled, returns None (all requests allowed).
    """
    if not AUTH_ENABLED:
        return None

    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header.")

    user_id = API_KEY_MAP.get(x_api_key)
    if user_id is None:
        raise HTTPException(status_code=403, detail="Invalid API key.")

    return user_id


# ── Endpoints ───────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Simple health check for load balancers and monitoring."""
    return {"status": "ok", "service": "secondcortex-backend", "auth_enabled": AUTH_ENABLED}


@app.post("/api/v1/snapshot", status_code=200)
async def receive_snapshot(
    payload: SnapshotPayload,
    background_tasks: BackgroundTasks,
    user_id: str | None = Depends(get_current_user),
):
    """
    Receive a sanitized IDE snapshot from the VS Code extension.
    Returns 200 OK instantly, then processes asynchronously via Retriever.
    """
    logger.info("Received snapshot for file: %s (user=%s)", payload.active_file, user_id or "anon")
    background_tasks.add_task(retriever.process_snapshot, payload, user_id)
    return {"status": "accepted", "message": "Snapshot queued for processing."}


@app.get("/api/v1/events")
async def get_events(user_id: str | None = Depends(get_current_user)):
    """
    Endpoint for the Next.js React Flow to poll recent snapshots.
    Scoped to the authenticated user's collection.
    """
    results = await vector_db.semantic_search("*", top_k=10, user_id=user_id)

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


@app.post("/api/v1/query", response_model=QueryResponse)
async def handle_query(
    request: QueryRequest,
    user_id: str | None = Depends(get_current_user),
):
    """
    Handle a user question — runs the Planner → Executor pipeline.
    """
    logger.info("Query received: %s (user=%s)", request.question, user_id or "anon")

    # Step 1: Plan — break the question into search tasks
    plan_result = await planner.plan(request.question, user_id=user_id)

    # Step 2: Execute — synthesize and validate
    response = await executor.synthesize(request.question, plan_result)

    logger.info("Query answered: %s", response.summary[:100])
    return response


@app.post("/api/v1/resurrect", response_model=ResurrectionResponse)
async def handle_resurrection(
    request: ResurrectionRequest,
    user_id: str | None = Depends(get_current_user),
):
    """
    Generate a Workspace Resurrection plan for a given target branch/snapshot.
    """
    logger.info("Resurrection requested for target: %s (user=%s)", request.target, user_id or "anon")

    plan_result = await planner.plan(
        f"Find the workspace state for branch or snapshot: {request.target}",
        user_id=user_id,
    )

    response = await executor.synthesize(
        f"Generate workspace resurrection commands for: {request.target}",
        plan_result,
    )

    return ResurrectionResponse(commands=response.commands)


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
