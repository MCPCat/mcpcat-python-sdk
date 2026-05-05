"""FastMCP v3 event-capture tests over real Streamable HTTP.

Initialize-event capture is intentionally omitted (handled by ServerSession
internally; see tests/e2e/official/test_event_capture_http.py docstring).
"""

from __future__ import annotations

import time

import pytest


pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_call_tool_via_v3(v3_http_server, capture_queue):
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, _ = v3_http_server
    async with Client(StreamableHttpTransport(url)) as client:
        await client.call_tool(
            "add_todo", {"text": "v3-call", "context": "x"}
        )

    time.sleep(0.5)
    call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
    assert call_events
    assert call_events[0].resource_name == "add_todo"


@pytest.mark.asyncio
async def test_list_tools_via_v3(v3_http_server, capture_queue):
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, _ = v3_http_server
    async with Client(StreamableHttpTransport(url)) as client:
        await client.list_tools()

    time.sleep(0.5)
    assert any(e.event_type == "mcp:tools/list" for e in capture_queue)


@pytest.mark.asyncio
async def test_v3_event_duration_is_non_negative(v3_http_server, capture_queue):
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, _ = v3_http_server
    async with Client(StreamableHttpTransport(url)) as client:
        await client.call_tool(
            "add_todo", {"text": "duration", "context": "x"}
        )

    time.sleep(0.5)
    call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
    assert call_events
    assert call_events[0].duration is not None
    assert call_events[0].duration >= 0
