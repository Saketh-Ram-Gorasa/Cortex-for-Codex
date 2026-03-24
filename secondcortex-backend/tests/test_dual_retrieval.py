"""
Unit tests for dual retrieval in query flow.
Tests that QueryResponse includes both retrieved_facts and retrieved_snapshots.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from uuid import uuid4

from models.schemas import Fact, QueryRequest, QueryResponse


@pytest.mark.asyncio
async def test_query_response_includes_facts():
    """Test that QueryResponse includes retrieved_facts field."""
    response = QueryResponse(
        summary="Test response",
        reasoningLog=["step 1", "step 2"],
        commands=[],
        retrieved_facts=[
            {"id": str(uuid4()), "content": "Peter specializes in optimization", "kind": "experience", "salience": 0.9},
            {"id": str(uuid4()), "content": "Database performance critical", "kind": "world", "salience": 0.7},
        ],
        retrieved_snapshots=[]
    )
    
    assert len(response.retrieved_facts) == 2
    assert response.retrieved_facts[0]["content"] == "Peter specializes in optimization"
    assert response.retrieved_facts[0]["kind"] == "experience"
    assert response.retrieved_facts[0]["salience"] == 0.9


@pytest.mark.asyncio
async def test_query_response_includes_snapshots():
    """Test that QueryResponse includes retrieved_snapshots field."""
    response = QueryResponse(
        summary="Test response",
        reasoningLog=[],
        commands=[],
        retrieved_facts=[],
        retrieved_snapshots=[
            {"id": "snap-1", "timestamp": "2025-01-15T10:30:00", "file": "main.py", "branch": "main"},
            {"id": "snap-2", "timestamp": "2025-01-15T10:31:00", "file": "utils.py", "branch": "feature/xyz"},
        ]
    )
    
    assert len(response.retrieved_snapshots) == 2
    assert response.retrieved_snapshots[0]["file"] == "main.py"
    assert response.retrieved_snapshots[1]["branch"] == "feature/xyz"


@pytest.mark.asyncio
async def test_query_response_with_both_facts_and_snapshots():
    """Test that QueryResponse can contain both facts and snapshots together."""
    response = QueryResponse(
        summary="Query result with dual retrieval",
        reasoningLog=["planned search", "executed search"],
        commands=[],
        retrieved_facts=[
            {"id": str(uuid4()), "content": "Fact 1", "kind": "world", "salience": 0.8},
        ],
        retrieved_snapshots=[
            {"id": "snap-1", "timestamp": "2025-01-15T10:30:00", "file": "test.py", "branch": "main"},
        ]
    )
    
    assert len(response.retrieved_facts) == 1
    assert len(response.retrieved_snapshots) == 1
    assert response.retrieved_facts[0]["content"] == "Fact 1"
    assert response.retrieved_snapshots[0]["file"] == "test.py"


@pytest.mark.asyncio
async def test_fact_serialization_via_alias():
    """Test that retrieved_facts can be serialized with camelCase alias."""
    response = QueryResponse(
        summary="Test",
        reasoningLog=[],
        commands=[],
        retrieved_facts=[{"id": "f1", "content": "test", "kind": "world", "salience": 0.5}],
        retrieved_snapshots=[]
    )
    
    # Serialize to dict using aliases
    data = response.model_dump(by_alias=True)
    assert "retrievedFacts" in data
    assert "retrievedSnapshots" in data
    assert len(data["retrievedFacts"]) == 1


@pytest.mark.asyncio
async def test_empty_facts_and_snapshots():
    """Test that response handles empty facts and snapshots gracefully."""
    response = QueryResponse(
        summary="No results found",
        reasoningLog=[],
        commands=[],
        retrieved_facts=[],
        retrieved_snapshots=[]
    )
    
    assert response.retrieved_facts == []
    assert response.retrieved_snapshots == []
    assert len(response.retrieved_facts) == 0
    assert len(response.retrieved_snapshots) == 0
