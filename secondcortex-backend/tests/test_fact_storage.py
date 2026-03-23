"""
Test suite for Fact storage and retrieval in the long-term memory system.
"""

import pytest
from datetime import datetime
from models.schemas import Fact
from services.vector_db import VectorDBService


@pytest.mark.asyncio
async def test_fact_upsert():
    """Test upserting a fact to the vector DB."""
    service = VectorDBService()
    fact = Fact(
        id="fact_001",
        content="Peter specializes in database optimization",
        kind="experience",
        salience=0.8,
        confidence=0.9,
        entities=["Peter", "database"],
        source_snapshot_id="snap_123",
        created_at=datetime.utcnow(),
        last_accessed_at=datetime.utcnow(),
    )
    
    await service.upsert_fact(fact, user_id="user_123")
    
    retrieved = await service.get_fact_by_id("fact_001", user_id="user_123")
    assert retrieved is not None
    assert retrieved["document"] == "Peter specializes in database optimization"  # Stored as document field
    assert retrieved["kind"] == "experience"
    assert float(retrieved["salience"]) == 0.8


@pytest.mark.asyncio
async def test_fact_recall():
    """Test recalling facts by query."""
    service = VectorDBService()
    
    fact1 = Fact(
        id="fact_001",
        content="Peter specializes in database optimization",
        kind="experience",
        salience=0.9,
        confidence=0.95,
        entities=["Peter", "database"],
        source_snapshot_id="snap_123",
        created_at=datetime.utcnow(),
        last_accessed_at=datetime.utcnow(),
    )
    
    fact2 = Fact(
        id="fact_002",
        content="Database indices improve query performance",
        kind="world",
        salience=0.7,
        confidence=0.9,
        entities=["database", "performance"],
        source_snapshot_id="snap_124",
        created_at=datetime.utcnow(),
        last_accessed_at=datetime.utcnow(),
    )
    
    await service.upsert_fact(fact1, user_id="user_123")
    await service.upsert_fact(fact2, user_id="user_123")
    
    results = await service.recall_facts("database optimization", top_k=5, user_id="user_123")
    assert len(results) >= 1
    assert any(r["id"] == "fact_001" for r in results)
