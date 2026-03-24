import asyncio

import mcp_server


def test_get_incident_packet_requires_auth(monkeypatch):
    monkeypatch.delenv("SECONDCORTEX_MCP_API_KEY", raising=False)
    mcp_server._rate_limiter._calls.clear()
    out = asyncio.run(mcp_server.get_incident_packet(question="why auth failed", api_key=None))
    assert "Authentication required" in out
