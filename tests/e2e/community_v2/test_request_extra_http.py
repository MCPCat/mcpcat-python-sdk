"""Community FastMCP v2 headers smoke.

Skips when v2 is not installed (the standard dev venv has v3).
"""

from __future__ import annotations

import time

import pytest


pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_v2_custom_header_lands_in_extra(v2_http_server, capture_queue):
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, _ = v2_http_server
    async with Client(
        StreamableHttpTransport(url, headers={"X-V2-Header": "v2-value"})
    ) as client:
        await client.call_tool(
            "add_todo", {"text": "v2-h", "context": "v2-h"}
        )

    time.sleep(0.5)
    call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
    assert call_events
    headers = (
        (call_events[0].parameters or {})
        .get("extra", {})
        .get("requestInfo", {})
        .get("headers", {})
    )
    assert headers.get("x-v2-header") == "v2-value", (
        f"expected x-v2-header in extra.requestInfo.headers, got {headers}"
    )
