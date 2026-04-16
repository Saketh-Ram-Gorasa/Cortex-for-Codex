"""Self-improving MCP adapter for local snapshot-backed learning.

This package is intentionally independent of the main backend MCP server.
It focuses on Codex workflow features:

1. Self-improving execution feedback capture and retrieval.
2. Failure-aware memory lookup with failure classification.
3. Claim validation against snapshot evidence from local ChromaDB.
"""

from .server import mcp

__all__ = ["mcp"]
