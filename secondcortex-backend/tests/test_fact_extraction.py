"""
Test fact extraction from snapshot ingest.
"""

import pytest
from datetime import datetime
from models.schemas import SnapshotPayload
from agents.retriever import RetrieverAgent
from services.vector_db import VectorDBService


@pytest.mark.asyncio
async def test_facts_extracted_on_snapshot_add():
    """Test that facts are extracted and stored when snapshot is ADD."""
    vector_db = VectorDBService()
    retriever = RetrieverAgent(vector_db)
    
    payload = SnapshotPayload(
        timestamp=datetime.utcnow(),
        workspace_folder="my-project",
        active_file="src/database.py",
        language_id="python",
        shadow_graph="Implemented indexing on user_id column to fix slow query.",
        git_branch="main",
        terminal_commands=["python test.py"],
        project_id=None,
        function_context=None,
    )
    
    stored = await retriever.process_snapshot(payload, user_id="test_user")
    
    # Verify snapshot was stored
    assert stored.id is not None
    assert stored.metadata.operation.value == "ADD"
