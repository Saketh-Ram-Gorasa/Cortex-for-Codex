"""
SecondCortex Backend — Pydantic models for request/response schemas.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Snapshot Payload (from VS Code extension) ────────────────────

class SnapshotPayload(BaseModel):
    """The sanitized IDE snapshot sent by the VS Code extension."""
    timestamp: datetime
    workspace_folder: str = Field(..., alias="workspaceFolder")
    active_file: str = Field(..., alias="activeFile")
    language_id: str = Field(..., alias="languageId")
    shadow_graph: str = Field(..., alias="shadowGraph")
    git_branch: str | None = Field(None, alias="gitBranch")
    terminal_commands: list[str] = Field(default_factory=list, alias="terminalCommands")

    model_config = {"populate_by_name": True}


# ── Memory Operations ───────────────────────────────────────────

class MemoryOperation(str, Enum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    NOOP = "NOOP"


class EntityRelation(BaseModel):
    source: str
    target: str
    relation: str


class MemoryMetadata(BaseModel):
    """Strict JSON metadata extracted by the Retriever agent."""
    operation: MemoryOperation
    entities: list[str] = Field(default_factory=list)
    relations: list[EntityRelation] = Field(default_factory=list)
    summary: str = ""


# ── Query (from Sidebar chat) ───────────────────────────────────

class QueryRequest(BaseModel):
    question: str


class ResurrectionCommand(BaseModel):
    type: str  # git_stash, git_checkout, open_file, split_terminal, run_command, open_workspace
    branch: str | None = None
    file_path: str | None = Field(None, alias="filePath")
    viewColumn: int | None = Field(None, alias="viewColumn")
    command: str | None = None

    model_config = {"populate_by_name": True}


class QueryResponse(BaseModel):
    summary: str
    reasoningLog: list[str] = Field(default_factory=list, alias="reasoningLog")
    commands: list[ResurrectionCommand] = Field(default_factory=list)


# ── Resurrection ────────────────────────────────────────────────

class ResurrectionRequest(BaseModel):
    target: str
    current_workspace: str | None = None


class SafetyReport(BaseModel):
    conflicts: list[str] = Field(default_factory=list)
    unstashed_changes: bool = False
    estimated_risk: str = "low"


class ResurrectionResponse(BaseModel):
    commands: list[ResurrectionCommand]
    impact_analysis: SafetyReport | None = None
    plan_summary: str | None = Field(None, alias="planSummary")


# ── Internal: stored snapshot record ────────────────────────────

class StoredSnapshot(BaseModel):
    id: str
    timestamp: datetime
    workspace_folder: str
    active_file: str
    language_id: str
    shadow_graph: str
    git_branch: str | None = None
    terminal_commands: list[str] = Field(default_factory=list)
    metadata: MemoryMetadata | None = None
    embedding: list[float] | None = None

# ── Chat History ────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: datetime


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessage]


class ChatSession(BaseModel):
    id: str
    title: str
    created_at: datetime


class ChatSessionsResponse(BaseModel):
    sessions: list[ChatSession]
