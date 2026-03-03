"""
SecondCortex Backend — FastAPI Main Server

Endpoints:
  POST /api/v1/snapshot  — Receives sanitized IDE snapshots (returns 200 instantly,
                           processes in background via Retriever).
  POST /api/v1/query     — Receives a user question, runs Planner → Executor pipeline.
  POST /api/v1/resurrect — Receives a target branch/snapshot ID, returns resurrection commands.
  GET  /health           — Health check.
"""

from __future__ import annotations

import logging

from fastapi import BackgroundTasks, FastAPI
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
from services.azure_integration import AzureIntegrationService

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
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Service & Agent Initialization ──────────────────────────────
azure_service = AzureIntegrationService()
retriever = RetrieverAgent(azure_service)
planner = PlannerAgent(azure_service)
executor = ExecutorAgent()


# ── Endpoints ───────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Simple health check for load balancers and monitoring."""
    return {"status": "ok", "service": "secondcortex-backend"}


@app.post("/api/v1/snapshot", status_code=200)
async def receive_snapshot(payload: SnapshotPayload, background_tasks: BackgroundTasks):
    """
    Receive a sanitized IDE snapshot from the VS Code extension.
    Returns 200 OK instantly, then processes asynchronously via Retriever.
    """
    logger.info("Received snapshot for file: %s", payload.active_file)
    background_tasks.add_task(retriever.process_snapshot, payload)
    return {"status": "accepted", "message": "Snapshot queued for processing."}


@app.get("/api/v1/events")
async def get_events():
    """
    Endpoint for the Next.js React Flow to poll recent snapshots.
    Fetches the latest context graph events from Azure AI Search.
    """
    # Fetch top 10 recent events using an empty search string (match all)
    results = await azure_service.semantic_search("*", top_k=10)
    
    # Map the search payload back into the event format expected by the frontend
    events = []
    for r in results:
        events.append({
            "id": r.get("id"),
            "timestamp": r.get("timestamp"),
            "active_file": r.get("active_file"),
            "git_branch": r.get("git_branch"),
            "summary": r.get("summary"),
            "entities": r.get("entities", "").split(",") if r.get("entities") else [],
            "relations": [] # Graph relations not fully projected in this basic search
        })
        
    return {"events": events}


@app.post("/api/v1/query", response_model=QueryResponse)
async def handle_query(request: QueryRequest):
    """
    Handle a user question — runs the Planner → Executor pipeline.
    """
    logger.info("Query received: %s", request.question)

    # Step 1: Plan — break the question into search tasks
    plan_result = await planner.plan(request.question)

    # Step 2: Execute — synthesize and validate
    response = await executor.synthesize(request.question, plan_result)

    logger.info("Query answered: %s", response.summary[:100])
    return response


@app.post("/api/v1/resurrect", response_model=ResurrectionResponse)
async def handle_resurrection(request: ResurrectionRequest):
    """
    Generate a Workspace Resurrection plan for a given target branch/snapshot.
    """
    logger.info("Resurrection requested for target: %s", request.target)

    # Use the planner to search for context around the target
    plan_result = await planner.plan(
        f"Find the workspace state for branch or snapshot: {request.target}"
    )

    # Use the executor to generate resurrection commands
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
