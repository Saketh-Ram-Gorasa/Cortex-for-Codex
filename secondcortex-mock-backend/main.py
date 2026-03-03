"""
SecondCortex Mock Backend — A local, no-Azure simulation for demo purposes.

This runs purely in memory and generates fake "AI reasoning" and context graph events
so you can test the VS Code extension and the Next.js frontend instantly.
"""

import logging
import random
import uuid
from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── Logging setup ───────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("mock_backend")

app = FastAPI(title="SecondCortex Mock API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-Memory Store ─────────────────────────────────────────────

# In a real app, this would be Azure AI Search or Cosmos DB
EVENTS_STORE: list[dict[str, Any]] = []

# ── Pydantic Models ─────────────────────────────────────────────

class SnapshotPayload(BaseModel):
    timestamp: datetime
    workspace_folder: str = Field(..., alias="workspaceFolder")
    active_file: str = Field(..., alias="activeFile")
    language_id: str = Field(..., alias="languageId")
    shadow_graph: str = Field(..., alias="shadowGraph")
    git_branch: str | None = Field(None, alias="gitBranch")
    terminal_commands: list[str] = Field(default_factory=list, alias="terminalCommands")

    model_config = {"populate_by_name": True}

class QueryRequest(BaseModel):
    question: str

class ResurrectionRequest(BaseModel):
    target: str


# ── Background Mock Processing ──────────────────────────────────

def mock_process_snapshot(payload: SnapshotPayload):
    """Simulates the Retriever agent processing a snapshot."""
    import time
    time.sleep(1)  # Simulate network/LLM delay

    # Generate some fake metadata based on the file name
    file_name = payload.active_file.split("/")[-1].split("\\")[-1]
    
    actions = [
        "Adding new feature to",
        "Debugging issue in",
        "Refactoring logic inside",
        "Writing tests for",
        "Updating configuration in"
    ]
    summary = f"{random.choice(actions)} {file_name}"
    
    event = {
        "id": str(uuid.uuid4()),
        "timestamp": payload.timestamp.isoformat(),
        "active_file": payload.active_file,
        "git_branch": payload.git_branch or "main",
        "summary": summary,
        "entities": [file_name, "user_session", "database_pool"],
        "relations": [
            {"source": file_name, "target": "database_pool", "relation": "depends_on"},
            {"source": "user_session", "target": file_name, "relation": "updated_by"}
        ]
    }
    
    EVENTS_STORE.append(event)
    logger.info("Mocked event added to graph: %s", summary)

# ── Endpoints ───────────────────────────────────────────────────

@app.get("/health")
def health_check():
    return {"status": "ok", "mode": "mock"}

@app.post("/api/v1/snapshot", status_code=200)
def receive_snapshot(payload: SnapshotPayload, background_tasks: BackgroundTasks):
    logger.info("Received mock snapshot for file: %s", payload.active_file)
    background_tasks.add_task(mock_process_snapshot, payload)
    return {"status": "accepted", "message": "Mock snapshot queued."}

@app.get("/api/v1/events")
def get_events():
    """Endpoint used by the Next.js React Flow to render nodes."""
    return {"events": EVENTS_STORE}

@app.post("/api/v1/query")
def handle_query(request: QueryRequest):
    logger.info("Mock query received: %s", request.question)
    return {
        "summary": "This is a mocked answer. The developer was recently working on the auth module based on the last 5 snapshots.",
        "reasoningLog": [
            "Step 1: Retrieved recent snapshots from the mock store.",
            "Step 2: Found evidence of branch `feature/auth-fix`.",
            "Step 3: Synthesized timeline successfully."
        ],
        "commands": []
    }

@app.post("/api/v1/resurrect")
def handle_resurrection(request: ResurrectionRequest):
    logger.info("Mock resurrection requested for: %s", request.target)
    return {
        "commands": [
            {"type": "git_stash"},
            {"type": "git_checkout", "branch": request.target},
            {"type": "open_file", "filePath": "src/extension.ts", "viewColumn": 1},
            {"type": "split_terminal", "command": "npm run dev"}
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
