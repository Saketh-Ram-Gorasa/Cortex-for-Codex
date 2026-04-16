"""
SecondCortex Backend — Pydantic models for request/response schemas.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

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
    project_id: str | None = Field(None, alias="projectId")
    terminal_commands: list[str] = Field(default_factory=list, alias="terminalCommands")
    capture_level: Literal["base", "medium", "full", "ultra"] = Field("medium", alias="captureLevel")
    capture_meta: dict[str, Any] = Field(default_factory=dict, alias="captureMeta")
    function_context: dict[str, Any] | None = Field(None, alias="functionContext")

    model_config = {"populate_by_name": True}


class CommentCapture(BaseModel):
    type: Literal["inline", "block", "jsdoc", "todo", "fixme", "hack"]
    content: str = ""
    line: int = 0
    function_context: str = Field("global", alias="functionContext")
    is_new: bool = Field(False, alias="isNew")

    model_config = {"populate_by_name": True}


class TodoCapture(BaseModel):
    type: Literal["TODO", "FIXME", "HACK", "NOTE", "TEMP"]
    content: str = ""
    file: str = ""
    function_context: str = Field("global", alias="functionContext")
    age: Literal["new", "existing"] = "existing"

    model_config = {"populate_by_name": True}


class EnrichedComments(BaseModel):
    new: list[CommentCapture] = Field(default_factory=list)
    existing: list[CommentCapture] = Field(default_factory=list)
    todos: list[TodoCapture] = Field(default_factory=list)


class RecentCommit(BaseModel):
    hash: str = ""
    message: str = ""
    files_changed: list[str] = Field(default_factory=list, alias="filesChanged")
    timestamp: int = 0
    author: str = ""

    model_config = {"populate_by_name": True}


class DiffStats(BaseModel):
    files_modified: int = Field(0, alias="filesModified")
    insertions: int = 0
    deletions: int = 0
    changed_files: list[str] = Field(default_factory=list, alias="changedFiles")

    model_config = {"populate_by_name": True}


class DiagnosticsSnapshot(BaseModel):
    errors: int = 0
    warnings: int = 0
    error_messages: list[str] = Field(default_factory=list, alias="errorMessages")

    model_config = {"populate_by_name": True}


class ExtensionSignals(BaseModel):
    debug_session_active: bool = Field(False, alias="debugSessionActive")
    debug_adapter_type: str = Field("none", alias="debugAdapterType")
    breakpoint_count: int = Field(0, alias="breakpointCount")
    test_runner_active: bool = Field(False, alias="testRunnerActive")
    active_terminal_count: int = Field(0, alias="activeTerminalCount")

    model_config = {"populate_by_name": True}


class SearchQueryCapture(BaseModel):
    query: str = ""
    results: int = 0
    file_types: list[str] = Field(default_factory=list, alias="fileTypes")

    model_config = {"populate_by_name": True}


class ImportChanges(BaseModel):
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)


class FunctionSignatures(BaseModel):
    changed: list[str] = Field(default_factory=list)
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)


class TestResults(BaseModel):
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration: int = 0


class EnrichedSnapshot(BaseModel):
    comments: EnrichedComments = Field(default_factory=EnrichedComments)
    recent_commits: list[RecentCommit] = Field(default_factory=list, alias="recentCommits")
    diff_stats: DiffStats = Field(default_factory=DiffStats, alias="diffStats")
    diagnostics: DiagnosticsSnapshot = Field(default_factory=DiagnosticsSnapshot)
    extension_signals: ExtensionSignals = Field(default_factory=ExtensionSignals, alias="extensionSignals")
    search_queries: list[SearchQueryCapture] = Field(default_factory=list, alias="searchQueries")
    import_changes: ImportChanges = Field(default_factory=ImportChanges, alias="importChanges")
    function_signatures: FunctionSignatures = Field(default_factory=FunctionSignatures, alias="functionSignatures")
    test_results: TestResults | None = Field(None, alias="testResults")

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


# ── Long-Term Memory: Facts ────────────────────────────────────

class Fact(BaseModel):
    """Long-term memory: an explicit fact extracted or retained."""
    id: str                          # UUID
    content: str                     # The fact text (e.g., "Peter specializes in optimization")
    kind: str                        # "world" | "experience" | "opinion" | "entity"
    salience: float = 0.5            # 0.0-1.0: importance/relevance
    confidence: float = 0.7          # 0.0-1.0: certainty
    entities: list[str] = Field(default_factory=list)  # Related entity names
    source_snapshot_id: str | None = None  # Snapshot this was extracted from
    created_at: datetime             # When fact was created
    last_accessed_at: datetime       # When fact was last retrieved (for decay)

    model_config = {"populate_by_name": True}


# ── Query (from Sidebar chat) ───────────────────────────────────

class QueryRequest(BaseModel):
    question: str


class IncidentPacketRequest(BaseModel):
    question: str
    project_id: str | None = Field(None, alias="projectId")
    time_window: str = Field("24h", alias="timeWindow")

    model_config = {"populate_by_name": True}


class IncidentHypothesis(BaseModel):
    id: str
    rank: int
    cause: str
    confidence: float
    supporting_evidence_ids: list[str] = Field(default_factory=list, alias="supportingEvidenceIds")

    model_config = {"populate_by_name": True}


class IncidentRecoveryOption(BaseModel):
    strategy: str
    risk: str
    blast_radius: str = Field(..., alias="blastRadius")
    estimated_time_minutes: int = Field(..., alias="estimatedTimeMinutes")
    commands: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class IncidentContradiction(BaseModel):
    evidence_a_id: str = Field(..., alias="evidenceAId")
    evidence_b_id: str = Field(..., alias="evidenceBId")
    note: str

    model_config = {"populate_by_name": True}


class IncidentEvidenceNode(BaseModel):
    id: str
    type: str
    timestamp: str
    file: str
    branch: str
    summary: str
    source: str


class IncidentPacketResponse(BaseModel):
    incident_id: str = Field(..., alias="incidentId")
    summary: str
    confidence: float
    hypotheses: list[IncidentHypothesis] = Field(default_factory=list)
    recovery_options: list[IncidentRecoveryOption] = Field(default_factory=list, alias="recoveryOptions")
    contradictions: list[str] = Field(default_factory=list)
    evidence_nodes: list[IncidentEvidenceNode] = Field(default_factory=list, alias="evidenceNodes")
    disproof_checks: list[str] = Field(default_factory=list, alias="disproofChecks")

    model_config = {"populate_by_name": True}


class ResurrectionCommand(BaseModel):
    type: str  # git_stash, git_checkout, open_file, split_terminal, run_command, open_workspace
    branch: str | None = None
    file_path: str | None = Field(None, alias="filePath")
    viewColumn: int | None = Field(None, alias="viewColumn")
    command: str | None = None

    model_config = {"populate_by_name": True}


class HumanInteractionDecision(BaseModel):
    action_id: str = Field(..., alias="actionId")
    command_type: str = Field(..., alias="commandType")
    decision: Literal["allow", "ask", "deny"]
    risk: Literal["low", "medium", "high", "critical"]
    reason: str
    command_preview: str = Field("", alias="commandPreview")

    model_config = {"populate_by_name": True}


class HumanInteractionEnvelope(BaseModel):
    mode: Literal["allow", "prompt", "read_only"]
    requires_confirmation: bool = Field(False, alias="requiresConfirmation")
    prompt: str = ""
    decisions: list[HumanInteractionDecision] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list, alias="allowedActions")
    denied_actions: list[str] = Field(default_factory=list, alias="deniedActions")

    model_config = {"populate_by_name": True}


class QueryResponse(BaseModel):
    summary: str
    reasoningLog: list[str] = Field(default_factory=list, alias="reasoningLog")
    commands: list[ResurrectionCommand] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    retrieved_facts: list[dict] = Field(default_factory=list, alias="retrievedFacts")
    retrieved_snapshots: list[dict] = Field(default_factory=list, alias="retrievedSnapshots")
    interaction: HumanInteractionEnvelope | None = None

    model_config = {"populate_by_name": True}


class DocumentIngestRequest(BaseModel):
    filename: str
    content_base64: str = Field(..., alias="contentBase64")
    domain: str
    source_uri: str | None = Field(None, alias="sourceUri")
    project_id: str | None = Field(None, alias="projectId")

    model_config = {"populate_by_name": True}


class DocumentIngestResponse(BaseModel):
    status: str
    record_id: str = Field(..., alias="recordId")
    source_type: str = Field(..., alias="sourceType")
    confidence: float = 0.0
    entities: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


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
    interaction: HumanInteractionEnvelope | None = None


# ── Retroactive Git Ingestion ───────────────────────────────

class RetroIngestRequest(BaseModel):
    repo_path: str | None = Field(None, alias="repoPath")
    max_commits: int = Field(120, alias="maxCommits")
    max_pull_requests: int = Field(30, alias="maxPullRequests")
    include_pull_requests: bool = Field(True, alias="includePullRequests")
    project_id: str | None = Field(None, alias="projectId")

    model_config = {"populate_by_name": True}


class RetroIngestResponse(BaseModel):
    status: str
    repo: str
    branch: str
    ingested_count: int = Field(alias="ingestedCount")
    commit_count: int = Field(alias="commitCount")
    pr_count: int = Field(alias="prCount")
    comment_count: int = Field(alias="commentCount")
    skipped_count: int = Field(alias="skippedCount")
    warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ── Decision Archaeology ───────────────────────────────────────

class ArchaeologyRequest(BaseModel):
    file_path: str = Field(..., alias="filePath")
    symbol_name: str = Field(..., alias="symbolName")
    signature: str
    commit_hash: str = Field(..., alias="commitHash")
    commit_message: str = Field("", alias="commitMessage")
    author: str = ""
    timestamp: datetime
    project_id: str | None = Field(None, alias="projectId")

    model_config = {"populate_by_name": True}


class ArchaeologyResponse(BaseModel):
    found: bool
    summary: str | None = None
    branches_tried: list[str] = Field(default_factory=list, alias="branchesTried")
    terminal_commands: list[str] = Field(default_factory=list, alias="terminalCommands")
    confidence: float = 0.0

    model_config = {"populate_by_name": True}


# ── Internal: stored snapshot record ────────────────────────────

class StoredSnapshot(BaseModel):
    id: str
    timestamp: datetime
    workspace_folder: str
    active_file: str
    language_id: str
    shadow_graph: str
    git_branch: str | None = None
    project_id: str | None = None
    terminal_commands: list[str] = Field(default_factory=list)
    capture_level: Literal["base", "medium", "full", "ultra"] = "medium"
    capture_meta: dict[str, Any] = Field(default_factory=dict)
    function_context: dict[str, Any] | None = None
    metadata: MemoryMetadata | None = None
    embedding: list[float] | None = None


class ProjectResolveRequest(BaseModel):
    workspace_name: str = Field("", alias="workspaceName")
    workspace_path_hash: str = Field("", alias="workspacePathHash")
    repo_remote: str = Field("", alias="repoRemote")
    team_id: str | None = Field(None, alias="teamId")

    model_config = {"populate_by_name": True}


class ProjectResolveCandidate(BaseModel):
    project_id: str = Field(..., alias="projectId")
    name: str
    confidence: float

    model_config = {"populate_by_name": True}


class ProjectResolveResponse(BaseModel):
    status: Literal["resolved", "ambiguous", "unresolved"]
    project_id: str | None = Field(None, alias="projectId")
    confidence: float = 0.0
    candidates: list[ProjectResolveCandidate] = Field(default_factory=list)
    needs_selection: bool = Field(False, alias="needsSelection")

    model_config = {"populate_by_name": True}

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


# ── Team Summaries ─────────────────────────────────────────────

class MemberSummary(BaseModel):
    """Summary metrics for a team member."""
    user_id: str
    display_name: str
    email: str
    snapshots_count: int
    commits_count: int
    languages_used: list[str] = Field(default_factory=list)
    files_modified: int = 0
    status: str = "active"  # "active", "idle", "inactive"


class TeamDailySummary(BaseModel):
    """Daily summary for a team."""
    team_id: str
    period: str = "daily"
    members: list[MemberSummary]
    total_snapshots: int = 0
    total_commits: int = 0
    active_members: int = 0
    generated_at: datetime


class TeamWeeklySummary(BaseModel):
    """Weekly summary for a team."""
    team_id: str
    period: str = "weekly"
    members: list[MemberSummary]
    total_snapshots: int = 0
    total_commits: int = 0
    active_members: int = 0
    daily_breakdown: dict[str, int] = Field(default_factory=dict)  # day -> snapshot_count
    generated_at: datetime
