"""
SecondCortex Backend — FastAPI Main Server

Endpoints:
  POST /api/v1/auth/signup  — Create a new account.
  POST /api/v1/auth/login   — Log in and get a JWT token.
  POST /api/v1/snapshot     — Receives sanitized IDE snapshots.
  POST /api/v1/query        — User question → Planner → Executor pipeline.
  POST /api/v1/resurrect    — Generate resurrection commands.
  GET  /api/v1/events       — Poll recent snapshots for the Live Graph.
  GET  /health              — Health check.
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

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agents.executor import ExecutorAgent
from agents.planner import PlannerAgent
from agents.retriever import RetrieverAgent
from auth.jwt_handler import verify_token
from auth.routes import router as auth_router
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
    version="0.3.0",
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

# ── Include auth routes ─────────────────────────────────────────
app.include_router(auth_router)

# ── Service & Agent Initialization ──────────────────────────────
vector_db = VectorDBService()
retriever = RetrieverAgent(vector_db)
planner = PlannerAgent(vector_db)
executor = ExecutorAgent()

# ── JWT Auth dependency ─────────────────────────────────────────
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """
    Validates the Bearer JWT token and returns the user_id.
    Every protected endpoint requires a valid token.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header. Please log in.")

    payload = verify_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token. Please log in again.")

    return payload["sub"]  # user_id


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
    logger.info("Received snapshot for file: %s (user=%s)", payload.active_file, user_id)
    background_tasks.add_task(retriever.process_snapshot, payload, user_id)
    return {"status": "accepted", "message": "Snapshot queued for processing."}


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


@app.post("/api/v1/query", response_model=QueryResponse)
async def handle_query(
    request: QueryRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Handle a user question — runs the Planner → Executor pipeline.
    """
    logger.info("Query received: %s (user=%s)", request.question, user_id)

    # Step 1: Plan — break the question into search tasks
    plan_result = await planner.plan(request.question, user_id=user_id)

    # Step 2: Execute — synthesize and validate
    response = await executor.synthesize(request.question, plan_result)

    logger.info("Query answered: %s", response.summary[:100])
    return response


@app.post("/api/v1/resurrect", response_model=ResurrectionResponse)
async def handle_resurrection(
    request: ResurrectionRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Generate a Workspace Resurrection plan for a given target branch/snapshot.
    """
    logger.info("Resurrection requested for target: %s (user=%s)", request.target, user_id)

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
