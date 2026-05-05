"""parameters.extra.requestInfo.headers parity for FastMCP v3 over real HTTP."""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.e2e


def _last_call(capture_queue):
    return [e for e in capture_queue if e.event_type == "mcp:tools/call"][-1]


def _extra(event):
    return (event.parameters or {}).get("extra", {})


@pytest.mark.asyncio
async def test_custom_header_lands_in_extra(v3_http_server, capture_queue):
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, _ = v3_http_server
    async with Client(
        StreamableHttpTransport(url, headers={"X-V3-Header": "v3-value"})
    ) as client:
        await client.call_tool(
            "add_todo", {"text": "v3-h", "context": "v3-h"}
        )

    time.sleep(0.5)
    headers = _extra(_last_call(capture_queue)).get("requestInfo", {}).get(
        "headers", {}
    )
    assert headers.get("x-v3-header") == "v3-value", (
        f"expected x-v3-header in extra.requestInfo.headers, got {headers}"
    )


@pytest.mark.asyncio
async def test_list_tools_event_carries_headers_via_v3(
    v3_http_server, capture_queue
):
    """tools/list events under v3 transport carry parameters.extra. This
    exercises the v3 middleware pipeline including the FastMCP
    `_current_http_request` ContextVar fallback path."""
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, _ = v3_http_server
    async with Client(
        StreamableHttpTransport(url, headers={"X-V3-List": "list-v"})
    ) as client:
        await client.list_tools()

    time.sleep(0.5)
    list_events = [e for e in capture_queue if e.event_type == "mcp:tools/list"]
    assert list_events
    headers = (
        (list_events[0].parameters or {})
        .get("extra", {})
        .get("requestInfo", {})
        .get("headers", {})
    )
    assert headers.get("x-v3-list") == "list-v", (
        f"expected x-v3-list on tools/list event, got headers={headers}"
    )


@pytest.mark.asyncio
async def test_meta_dict_present_when_supported(v3_http_server, capture_queue):
    """Sanity: extra.meta is either absent or a dict — never a malformed value."""
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, _ = v3_http_server
    async with Client(StreamableHttpTransport(url)) as client:
        await client.call_tool(
            "add_todo", {"text": "v3-meta", "context": "meta"}
        )

    time.sleep(0.5)
    extra = _extra(_last_call(capture_queue))
    meta = extra.get("meta")
    if meta is not None:
        assert isinstance(meta, dict)
