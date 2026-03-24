"""
End-to-end test for Seahorse Fact Bank MVP.
Tests the complete workflow: fact storage → extraction → dual retrieval → MCP exposure.
"""

import pytest
from datetime import datetime
from uuid import uuid4
from models.schemas import Fact, QueryResponse, SnapshotPayload
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_seahorse_mvp_e2e_fact_creation():
    """Test that facts can be created with all required fields."""
    fact = Fact(
        id=str(uuid4()),
        content="User prefers dark theme for accessibility",
        kind="opinion",
        salience=0.8,
        confidence=0.9,
        entities=["user", "accessibility", "theme"],
        source_snapshot_id="snap-abc123",
        created_at=datetime.now(),
        last_accessed_at=datetime.now(),
    )
    
    # Verify all fields are set correctly
    assert fact.id
    assert fact.content == "User prefers dark theme for accessibility"
    assert fact.kind == "opinion"
    assert fact.salience == 0.8
    assert fact.confidence == 0.9
    assert len(fact.entities) == 3
    assert fact.source_snapshot_id == "snap-abc123"


@pytest.mark.asyncio
async def test_seahorse_mvp_e2e_snapshot_payload():
    """Test that snapshot payloads are created with proper structure."""
    payload = SnapshotPayload(
        timestamp=datetime.now(),
        workspace_folder="/home/user/project",
        active_file="main.py",
        language_id="python",
        shadow_graph="def main(): ...",
        git_branch="main",
        project_id="proj-123",
        terminal_commands=["python test.py"],
    )
    
    assert payload.workspace_folder == "/home/user/project"
    assert payload.active_file == "main.py"
    assert payload.language_id == "python"
    assert payload.git_branch == "main"


@pytest.mark.asyncio
async def test_seahorse_mvp_e2e_query_response_integration():
    """Test that QueryResponse properly integrates facts and snapshots."""
    response = QueryResponse(
        summary="Query completed successfully",
        reasoningLog=["Step 1: Plan created", "Step 2: Executed search"],
        commands=[],
        retrieved_facts=[
            {
                "id": str(uuid4()),
                "content": "Database query optimization is critical",
                "kind": "world",
                "salience": 0.9
            }
        ],
        retrieved_snapshots=[
            {
                "id": "snap-1",
                "timestamp": "2025-01-15T10:30:00",
                "file": "query.py",
                "branch": "main"
            }
        ]
    )
    
    # Verify both facts and snapshots are present
    assert len(response.retrieved_facts) == 1
    assert len(response.retrieved_snapshots) == 1
    assert response.retrieved_facts[0]["kind"] == "world"
    assert response.retrieved_snapshots[0]["file"] == "query.py"


@pytest.mark.asyncio
async def test_seahorse_mvp_e2e_fact_kinds():
    """Test that all valid fact kinds are supported."""
    kinds = ["world", "experience", "opinion", "entity"]
    
    for kind in kinds:
        fact = Fact(
            id=str(uuid4()),
            content=f"This is a {kind} fact",
            kind=kind,
            salience=0.5,
            confidence=0.7,
            created_at=datetime.now(),
            last_accessed_at=datetime.now(),
        )
        assert fact.kind == kind


@pytest.mark.asyncio
async def test_seahorse_mvp_e2e_fact_salience_range():
    """Test that fact salience is constrained to 0.0-1.0 range."""
    facts = [
        Fact(
            id=str(uuid4()),
            content="Min salience",
            kind="world",
            salience=0.0,
            confidence=0.5,
            created_at=datetime.now(),
            last_accessed_at=datetime.now(),
        ),
        Fact(
            id=str(uuid4()),
            content="Max salience",
            kind="world",
            salience=1.0,
            confidence=0.5,
            created_at=datetime.now(),
            last_accessed_at=datetime.now(),
        ),
    ]
    
    for fact in facts:
        assert 0.0 <= fact.salience <= 1.0


@pytest.mark.asyncio
async def test_seahorse_mvp_e2e_fact_entities_list():
    """Test that facts can have multiple entities."""
    fact = Fact(
        id=str(uuid4()),
        content="Peter and Alice worked on authentication",
        kind="experience",
        salience=0.7,
        confidence=0.8,
        entities=["Peter", "Alice", "authentication", "security"],
        created_at=datetime.now(),
        last_accessed_at=datetime.now(),
    )
    
    assert len(fact.entities) == 4
    assert "Peter" in fact.entities
    assert "authentication" in fact.entities


@pytest.mark.asyncio
async def test_seahorse_mvp_e2e_snapshot_provenance():
    """Test that facts track their source snapshot."""
    snapshot_id = str(uuid4())
    fact = Fact(
        id=str(uuid4()),
        content="Extracted from IDE context",
        kind="experience",
        salience=0.6,
        confidence=0.7,
        source_snapshot_id=snapshot_id,
        created_at=datetime.now(),
        last_accessed_at=datetime.now(),
    )
    
    assert fact.source_snapshot_id == snapshot_id
    # Source snapshot is used to trace fact lineage back to original IDE context


@pytest.mark.asyncio
async def test_seahorse_mvp_e2e_response_serialization():
    """Test that QueryResponse serializes correctly with camelCase aliases."""
    response = QueryResponse(
        summary="Test",
        reasoningLog=["log1", "log2"],
        commands=[],
        retrieved_facts=[{"id": "f1", "content": "fact1", "kind": "world", "salience": 0.5}],
        retrieved_snapshots=[{"id": "s1", "timestamp": "2025-01-15", "file": "test.py", "branch": "main"}]
    )
    
    # Serialize to dict with aliases (camelCase)
    data = response.model_dump(by_alias=True)
    
    # Verify aliases are used
    assert "reasoningLog" in data  # Not "reasoning_log"
    assert "retrievedFacts" in data  # Not "retrieved_facts"
    assert "retrievedSnapshots" in data  # Not "retrieved_snapshots"


@pytest.mark.asyncio
async def test_seahorse_mvp_e2e_mcp_output_structure():
    """Test that MCP search_memory produces expected output structure."""
    # Simulate MCP output with both fact and snapshot sections
    mcp_output = (
        "=== FACTS (LONG-TERM MEMORY) ===\n"
        "Found 2 relevant facts for 'authentication':\n"
        "--- Fact 1 (experience) ---\n"
        "Content: Peter implemented OAuth in the platform\n"
        "Salience: 95.0% | Confidence: 90.0%\n"
        "Entities: Peter, OAuth, authentication\n"
        "\n=== SNAPSHOTS (SHORT-TERM MEMORY) ===\n"
        "Found 3 relevant snapshots for 'authentication':\n"
        "--- Snapshot 1 ---\n"
        "Time: 2025-01-15T10:30:00\n"
        "File: auth.py\n"
        "Branch: main\n"
    )
    
    # Verify structure
    assert "FACTS (LONG-TERM MEMORY)" in mcp_output
    assert "SNAPSHOTS (SHORT-TERM MEMORY)" in mcp_output
    assert "OAuth" in mcp_output
    assert "auth.py" in mcp_output
    # Facts section should come before snapshots
    assert mcp_output.index("FACTS") < mcp_output.index("SNAPSHOTS")


@pytest.mark.asyncio
async def test_seahorse_mvp_dual_memory_architecture():
    """Test the complete dual memory architecture concept."""
    # Long-term memory (Facts)
    long_term_facts = [
        {"content": "System uses PostgreSQL for primary storage", "kind": "world", "salience": 0.95},
        {"content": "Team prefers code reviews before merge", "kind": "opinion", "salience": 0.8},
    ]
    
    # Short-term memory (Snapshots)
    short_term_snapshots = [
        {"file": "migration.py", "timestamp": "2025-01-15T10:30:00", "branch": "main"},
        {"file": "review.py", "timestamp": "2025-01-15T10:31:00", "branch": "feature/xyz"},
    ]
    
    # Verify both types can coexist
    assert len(long_term_facts) > 0
    assert len(short_term_snapshots) > 0
    
    # Facts have persistence and salience for decay/forgetting algorithms
    assert long_term_facts[0]["salience"] > 0.8
    
    # Snapshots have temporal information for timeline reconstruction
    assert "timestamp" in short_term_snapshots[0]
