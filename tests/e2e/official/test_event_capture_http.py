"""Event-capture and round-trip tests over real Streamable HTTP.

NOTE: mcp:initialize events are not captured under any transport because
ServerSession handles initialize internally before user request handlers
fire (see the skipped in-memory test_initialization_event_capture). All
assertions in this file use post-initialize events instead.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_tools_list_event_captured(official_http_server, capture_queue):
    """Real handshake + list_tools produces a mcp:tools/list event."""
    url, _server = official_http_server
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await client.list_tools()

    time.sleep(0.5)
    list_events = [e for e in capture_queue if e.event_type == "mcp:tools/list"]
    assert list_events, (
        f"expected mcp:tools/list, got {[e.event_type for e in capture_queue]}"
    )


@pytest.mark.asyncio
async def test_tools_call_event_captured(official_http_server, capture_queue):
    url, _server = official_http_server
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await client.call_tool(
                "add_todo", {"text": "hi", "context": "e2e smoke"}
            )

    time.sleep(0.5)
    call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
    assert call_events, "expected a mcp:tools/call event"
    assert call_events[0].resource_name == "add_todo"


@pytest.mark.asyncio
async def test_event_duration_is_non_negative(official_http_server, capture_queue):
    """Tool round-trip records a non-negative duration."""
    url, _server = official_http_server
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await client.call_tool(
                "add_todo", {"text": "duration test", "context": "duration"}
            )

    time.sleep(0.5)
    call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
    assert call_events, "expected a mcp:tools/call event"
    assert call_events[0].duration is not None
    assert call_events[0].duration >= 0


@pytest.mark.asyncio
async def test_concurrent_clients_get_distinct_session_ids(
    official_http_server, capture_queue
):
    """Two stateful clients connecting concurrently should produce events with
    distinct mcp-session-id values in extra.sessionId."""
    url, _server = official_http_server

    async def call_once(text: str) -> None:
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                await client.call_tool(
                    "add_todo", {"text": text, "context": "concurrent"}
                )

    await asyncio.gather(call_once("a"), call_once("b"))
    time.sleep(0.7)

    call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
    assert len(call_events) >= 2, f"expected >=2 call events, got {len(call_events)}"
    session_ids = {
        (e.parameters or {}).get("extra", {}).get("sessionId") for e in call_events
    }
    # Each connection gets its own MCP session id.
    assert len(session_ids - {None}) >= 2, (
        f"expected distinct sessionIds across concurrent clients, got {session_ids}"
    )
