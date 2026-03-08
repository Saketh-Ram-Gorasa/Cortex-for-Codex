import sys
import os
import asyncio
import json

# Add backend to path
backend_path = r"c:\Users\SUHAAN\Desktop\SecondCortex Labs\code\secondcortex-backend"
sys.path.append(backend_path)

from services.vector_db import VectorDBService
from mcp_server import mcp

from datetime import datetime
import uuid

class MockMetadata:
    def __init__(self, summary, entities):
        self.summary = summary
        self.entities = entities

class MockSnapshot:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", uuid.uuid4())
        self.timestamp = kwargs.get("timestamp", datetime.now())
        self.workspace_folder = kwargs.get("workspace_folder", "")
        self.active_file = kwargs.get("active_file", "")
        self.language_id = kwargs.get("language_id", "python")
        self.shadow_graph = kwargs.get("shadow_graph", "")
        self.git_branch = kwargs.get("git_branch", "main")
        self.metadata = MockMetadata(kwargs.get("summary", ""), kwargs.get("entities", []))
        self.embedding = kwargs.get("embedding", [0.1] * 1536) # Dummy embedding

async def test_mcp():
    import mcp_server
    
    # Mock embedding generation on the server's global vector_db
    async def mock_embedding(text):
        return [0.1] * 1536
    
    mcp_server.vector_db.generate_embedding = mock_embedding
    db = mcp_server.vector_db
    
    # 1. Inject a test snapshot so the search has something to find
    print("Injecting test snapshot into ChromaDB...")
    mock_snap = MockSnapshot(
        active_file="auth_logic.py",
        git_branch="feat/mcp-test",
        summary="Implementing a secure authentication layer with JWT tokens.",
        shadow_graph="def login():\n    return 'success'",
        entities=["auth", "jwt", "login"]
    )
    await db.upsert_snapshot(mock_snap, user_id="test_user")
    
    print("Wait for indexing...")
    await asyncio.sleep(1)

    # 2. Call the MCP tool logic directly to verify result formatting
    print("\nCalling MCP tool: search_memory('authentication')...")
    from mcp_server import search_memory
    result = await search_memory(query="authentication", top_k=1, user_id="test_user")
    
    print("\nMCP Tool Result:")
    print("-" * 50)
    print(result)
    print("-" * 50)

if __name__ == "__main__":
    asyncio.run(test_mcp())
