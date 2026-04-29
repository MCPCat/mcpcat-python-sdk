"""Event-capture smoke and round-trip tests over real Streamable HTTP."""

from __future__ import annotations

import time

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_tools_list_event_captured(official_http_server, capture_queue):
    """Smoke: real handshake + list_tools produces a mcp:tools/list event.

    NOTE: mcp:initialize events are not captured (the ServerSession handles
    initialize internally before reaching user request handlers — see the
    skipped in-memory test test_initialization_event_capture). All assertions
    use post-initialize events instead.
    """
    url, _server = official_http_server
    async with streamablehttp_client(url) as (read, write, _get_session_id):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await client.list_tools()

    time.sleep(0.5)
    list_events = [e for e in capture_queue if e.event_type == "mcp:tools/list"]
    assert list_events, (
        f"expected an mcp:tools/list event, got {[e.event_type for e in capture_queue]}"
    )
