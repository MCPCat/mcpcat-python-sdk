"""FastMCP v3 event-capture smoke."""

from __future__ import annotations

import time

import pytest


pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_call_tool_via_v3(v3_http_server, capture_queue):
    """Smoke: real handshake + tool call produces a mcp:tools/call event."""
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, _server = v3_http_server
    async with Client(StreamableHttpTransport(url)) as client:
        await client.call_tool("add_todo", {"text": "v3-call", "context": "x"})

    time.sleep(0.5)
    call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
    assert call_events, (
        f"expected mcp:tools/call, got {[e.event_type for e in capture_queue]}"
    )
