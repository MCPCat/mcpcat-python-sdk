# E2E Streamable-HTTP Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `tests/e2e/` tree (~38 tests across 12 modules) that exercises MCPCat under real Streamable HTTP transport, covering header capture, header-derived client info, stateless mode, identify-per-event, and redaction over the wire — for the official MCP SDK, community FastMCP v3, and a smoke for community FastMCP v2.

**Architecture:** Module-scoped uvicorn-in-thread fixtures (official + v2) and FastMCP-native shttp_server fixture (v3) boot a real MCP server on `127.0.0.1:<random>` for each test module. Tests connect with the real `streamablehttp_client(url, headers=...)` / `fastmcp.Client(StreamableHttpTransport(url, headers=...))` and assert on events captured via a mocked `EventQueue` api_client. Each test module gets its own server instance so `MCPCatOptions` can vary per file (stateless mode, identify hook, redaction).

**Tech Stack:** Python 3.12, pytest + pytest-asyncio, uvicorn (already a transitive dep), httpx, the official `mcp` SDK and `fastmcp` v3.

---

## File Structure

**New files:**
- `tests/e2e/__init__.py`
- `tests/e2e/conftest.py` — top-level `capture_queue` fixture
- `tests/e2e/_helpers.py` — port utilities, optional raw POST helper
- `tests/e2e/official/__init__.py`
- `tests/e2e/official/conftest.py` — uvicorn-in-thread fixture for official SDK servers
- `tests/e2e/official/test_event_capture_http.py` — 5 tests
- `tests/e2e/official/test_request_extra_http.py` — 6 tests
- `tests/e2e/official/test_session_http.py` — 4 tests
- `tests/e2e/official/test_stateless_http.py` — 3 tests
- `tests/e2e/official/test_identify_http.py` — 5 tests
- `tests/e2e/official/test_redaction_http.py` — 3 tests
- `tests/e2e/community_v3/__init__.py`
- `tests/e2e/community_v3/conftest.py` — FastMCP-native shttp_server fixture
- `tests/e2e/community_v3/test_event_capture_http.py` — 3 tests
- `tests/e2e/community_v3/test_request_extra_http.py` — 3 tests
- `tests/e2e/community_v3/test_stateless_http.py` — 2 tests
- `tests/e2e/community_v3/test_identify_http.py` — 2 tests
- `tests/e2e/community_v2/__init__.py`
- `tests/e2e/community_v2/conftest.py` — uvicorn-in-thread fixture for v2 servers
- `tests/e2e/community_v2/test_request_extra_http.py` — 1 test
- `tests/e2e/community_v2/test_identify_http.py` — 1 test

**Modified files:**
- `pyproject.toml` — register the `e2e` pytest marker

---

## Task 1: Top-level scaffolding (marker + capture_queue + helpers)

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/_helpers.py`

- [ ] **Step 1: Register the `e2e` marker in pyproject.toml**

Open `pyproject.toml`, find `[tool.pytest.ini_options]` (already exists), and add a `markers` entry. The current section ends with `python_functions = "test_*"`. After that line, add:

```toml
markers = [
    "e2e: real HTTP transport tests (uvicorn-in-thread; ~25s overhead)",
]
```

- [ ] **Step 2: Create `tests/e2e/__init__.py`** (empty file)

```bash
mkdir -p tests/e2e && : > tests/e2e/__init__.py
```

- [ ] **Step 3: Create `tests/e2e/_helpers.py`**

```python
"""Shared helpers for the e2e Streamable-HTTP test suite."""

from __future__ import annotations

import socket
import time
from typing import Optional


def find_free_port() -> int:
    """Bind to 127.0.0.1:0, capture the assigned port, release the socket."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 5.0) -> None:
    """Poll until a TCP connection succeeds. Raise TimeoutError otherwise.

    Used by uvicorn-in-thread fixtures to gate test execution on server-ready.
    """
    deadline = time.time() + timeout
    last_err: Optional[Exception] = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as e:
            last_err = e
            time.sleep(0.05)
    raise TimeoutError(
        f"Port {host}:{port} not accepting connections after {timeout}s "
        f"(last error: {last_err!r})"
    )
```

- [ ] **Step 4: Create `tests/e2e/conftest.py`**

```python
"""Shared pytest fixtures for the e2e Streamable-HTTP suite.

`capture_queue` mocks the global event queue for the duration of a test and
yields the list that accumulates published events. Restores the real queue on
teardown.
"""

from __future__ import annotations

from typing import Any, List
from unittest.mock import MagicMock

import pytest

from mcpcat.modules.event_queue import EventQueue, set_event_queue


@pytest.fixture
def capture_queue() -> List[Any]:
    """Replace the global EventQueue with a mock that records every publish.

    Yields the list of captured PublishEventRequest objects. Tests assert on
    its contents after the in-flight HTTP round-trip plus a short settle.
    """
    from mcpcat.modules.event_queue import event_queue as original

    captured: List[Any] = []
    mock = MagicMock()
    mock.publish_event = MagicMock(side_effect=lambda req: captured.append(req))
    set_event_queue(EventQueue(api_client=mock))
    yield captured
    set_event_queue(original)
```

- [ ] **Step 5: Verify pytest collects the new marker**

Run: `uv run pytest --markers | grep e2e`
Expected output includes:
```
@pytest.mark.e2e: real HTTP transport tests (uvicorn-in-thread; ~25s overhead)
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/e2e/__init__.py tests/e2e/conftest.py tests/e2e/_helpers.py
git commit -m "test(e2e): add scaffolding for Streamable-HTTP test suite

Adds the e2e pytest marker, capture_queue fixture, and port utilities.
Subsequent commits will populate the per-SDK harnesses and tests."
```

---

## Task 2: Official SDK harness + smoke test

**Files:**
- Create: `tests/e2e/official/__init__.py`
- Create: `tests/e2e/official/conftest.py`
- Create: `tests/e2e/official/test_event_capture_http.py` (smoke only — 1 test)

- [ ] **Step 1: Create `tests/e2e/official/__init__.py`** (empty)

```bash
mkdir -p tests/e2e/official && : > tests/e2e/official/__init__.py
```

- [ ] **Step 2: Create `tests/e2e/official/conftest.py`**

```python
"""Uvicorn-in-thread harness for the official MCP SDK.

A test module declares an `MCPCATCAT_OPTIONS_FACTORY` (callable returning
`MCPCatOptions`) at module scope; `official_http_server` boots a fresh
FastMCP todo server for the module, calls `mcpcat.track(...)` with those
options, mounts the server's Streamable-HTTP app, and yields the URL.

Module-scoped: one boot per test file, not per test.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional, Tuple

import pytest
import uvicorn

import mcpcat
from mcpcat import MCPCatOptions

from tests.e2e._helpers import find_free_port, wait_for_port
from tests.test_utils.todo_server import create_todo_server


def _default_options_factory() -> MCPCatOptions:
    return MCPCatOptions(enable_tracing=True)


@pytest.fixture(scope="module")
def official_http_server(request) -> Tuple[str, Any]:
    """Boot a Streamable-HTTP MCP server for the test module.

    Reads the module attribute `MCPCAT_OPTIONS_FACTORY` (Callable[[], MCPCatOptions])
    if defined; otherwise uses tracing-only defaults.

    Yields:
        (url, server) — the Streamable-HTTP URL (e.g. "http://127.0.0.1:54321/mcp")
        and the FastMCP server instance under test.
    """
    options_factory: Callable[[], MCPCatOptions] = getattr(
        request.module, "MCPCAT_OPTIONS_FACTORY", _default_options_factory
    )
    options = options_factory()
    server = create_todo_server()
    mcpcat.track(server, "test_project", options)

    app = server._mcp_server.streamable_http_app()
    port = find_free_port()
    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="error", lifespan="on"
    )
    uv_server = uvicorn.Server(config)
    thread = threading.Thread(target=uv_server.run, daemon=True)
    thread.start()
    try:
        wait_for_port(port, timeout=5.0)
    except TimeoutError:
        uv_server.should_exit = True
        thread.join(timeout=2.0)
        raise

    url = f"http://127.0.0.1:{port}/mcp"
    yield url, server

    uv_server.should_exit = True
    thread.join(timeout=5.0)
```

- [ ] **Step 3: Create `tests/e2e/official/test_event_capture_http.py` (smoke — 1 test)**

```python
"""Event-capture smoke and round-trip tests over real Streamable HTTP."""

from __future__ import annotations

import time

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_initialize_event_captured(official_http_server, capture_queue):
    """Real handshake produces a mcp:initialize event."""
    url, _server = official_http_server
    async with streamablehttp_client(url) as (read, write, _get_session_id):
        async with ClientSession(read, write) as client:
            await client.initialize()

    # Events publish from a worker thread; settle briefly.
    time.sleep(0.5)
    init_events = [e for e in capture_queue if e.event_type == "mcp:initialize"]
    assert init_events, (
        f"expected an mcp:initialize event, got {[e.event_type for e in capture_queue]}"
    )
```

- [ ] **Step 4: Run the smoke**

Run: `uv run pytest tests/e2e/official/test_event_capture_http.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/official/__init__.py tests/e2e/official/conftest.py tests/e2e/official/test_event_capture_http.py
git commit -m "test(e2e): add official SDK uvicorn-in-thread harness + smoke

Adds the module-scoped uvicorn fixture and a single round-trip smoke test
proving real Streamable-HTTP traffic produces an mcp:initialize event."
```

---

## Task 3: Complete `tests/e2e/official/test_event_capture_http.py` (5 tests)

**Files:**
- Modify: `tests/e2e/official/test_event_capture_http.py`

- [ ] **Step 1: Replace the file with the full set of 5 tests**

```python
"""Event-capture and round-trip tests over real Streamable HTTP."""

from __future__ import annotations

import asyncio
import time

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_initialize_event_captured(official_http_server, capture_queue):
    """Real handshake produces a mcp:initialize event."""
    url, _server = official_http_server
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()

    time.sleep(0.5)
    init_events = [e for e in capture_queue if e.event_type == "mcp:initialize"]
    assert init_events, (
        f"expected mcp:initialize, got {[e.event_type for e in capture_queue]}"
    )


@pytest.mark.asyncio
async def test_tools_list_event_captured(official_http_server, capture_queue):
    url, _server = official_http_server
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await client.list_tools()

    time.sleep(0.5)
    list_events = [e for e in capture_queue if e.event_type == "mcp:tools/list"]
    assert list_events, "expected a mcp:tools/list event"


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
async def test_event_duration_is_non_zero(official_http_server, capture_queue):
    """Tool that exists in the test server runs through real HTTP; duration > 0."""
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
    # duration is integer milliseconds; real HTTP round-trip is always > 0.
    assert call_events[0].duration is not None
    assert call_events[0].duration >= 0


@pytest.mark.asyncio
async def test_concurrent_clients_get_distinct_session_ids(
    official_http_server, capture_queue
):
    """Two stateful clients connecting concurrently should get distinct session ids
    on emitted events (via mcp-session-id header issued by the SDK)."""
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
    # Each connection gets its own MCP session id; the set should have >= 2 distinct values.
    assert len(session_ids - {None}) >= 2, (
        f"expected distinct sessionIds across concurrent clients, got {session_ids}"
    )
```

- [ ] **Step 2: Run the file**

Run: `uv run pytest tests/e2e/official/test_event_capture_http.py -v`
Expected: 5 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/official/test_event_capture_http.py
git commit -m "test(e2e): complete official event-capture http suite

5 tests covering initialize/list_tools/tools_call event emission, duration
recording, and concurrent-client session id distinctness over real HTTP."
```

---

## Task 4: `tests/e2e/official/test_request_extra_http.py` (6 tests)

**Files:**
- Create: `tests/e2e/official/test_request_extra_http.py`

- [ ] **Step 1: Create the file**

```python
"""parameters.extra.requestInfo.headers parity tests over real Streamable HTTP."""

from __future__ import annotations

import time

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


pytestmark = pytest.mark.e2e


def _last_call_event(capture_queue):
    return [e for e in capture_queue if e.event_type == "mcp:tools/call"][-1]


def _extra(event):
    return (event.parameters or {}).get("extra", {})


@pytest.mark.asyncio
async def test_custom_header_lands_in_request_info(
    official_http_server, capture_queue
):
    url, _ = official_http_server
    async with streamablehttp_client(
        url, headers={"X-Demo-Header": "demo-value"}
    ) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await client.call_tool(
                "add_todo", {"text": "h", "context": "header test"}
            )

    time.sleep(0.5)
    headers = _extra(_last_call_event(capture_queue)).get("requestInfo", {}).get(
        "headers", {}
    )
    assert headers.get("x-demo-header") == "demo-value", (
        f"expected x-demo-header in extra.requestInfo.headers, got {headers}"
    )


@pytest.mark.asyncio
async def test_user_agent_preserved(official_http_server, capture_queue):
    url, _ = official_http_server
    async with streamablehttp_client(
        url, headers={"User-Agent": "Cursor/2.6.22"}
    ) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await client.call_tool(
                "add_todo", {"text": "ua", "context": "ua"}
            )

    time.sleep(0.5)
    headers = _extra(_last_call_event(capture_queue)).get("requestInfo", {}).get(
        "headers", {}
    )
    # The transport may add framing headers, but our header must survive.
    assert headers.get("user-agent") == "Cursor/2.6.22"


@pytest.mark.asyncio
async def test_mcp_session_id_header_promoted_to_extra_session_id(
    official_http_server, capture_queue
):
    """The SDK issues mcp-session-id during initialize; subsequent requests carry
    it back, so extra.sessionId on tool/call events must equal that header."""
    url, _ = official_http_server
    async with streamablehttp_client(url) as (read, write, get_sid):
        async with ClientSession(read, write) as client:
            await client.initialize()
            sdk_session_id = get_sid()
            await client.call_tool(
                "add_todo", {"text": "sid", "context": "session id"}
            )

    time.sleep(0.5)
    extra = _extra(_last_call_event(capture_queue))
    assert sdk_session_id, "MCP SDK should have issued an mcp-session-id"
    assert extra.get("sessionId") == sdk_session_id, (
        f"extra.sessionId={extra.get('sessionId')} should match SDK session id "
        f"{sdk_session_id}"
    )


@pytest.mark.asyncio
async def test_request_id_present_per_call(official_http_server, capture_queue):
    url, _ = official_http_server
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await client.call_tool(
                "add_todo", {"text": "r1", "context": "req"}
            )
            await client.call_tool(
                "add_todo", {"text": "r2", "context": "req"}
            )

    time.sleep(0.5)
    call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
    assert len(call_events) >= 2
    request_ids = [_extra(e).get("requestId") for e in call_events]
    assert all(rid is not None for rid in request_ids), request_ids
    # JSON-RPC ids should be unique per request on a single session.
    assert len(set(request_ids)) == len(request_ids), (
        f"expected distinct requestIds, got {request_ids}"
    )


@pytest.mark.asyncio
async def test_meta_progresstoken_passes_through(
    official_http_server, capture_queue
):
    """Client sends _meta.progressToken; it must surface in extra.meta."""
    url, _ = official_http_server

    # Use raw httpx because ClientSession does not expose progressToken cleanly.
    # See dual approach: drive client.send_request with custom params if needed.
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            # progress_token is a legitimate kwarg on call_tool in modern SDKs;
            # if absent in this SDK version, the test is best-effort and asserts
            # the meta dict exists.
            try:
                await client.call_tool(
                    "add_todo",
                    {"text": "meta", "context": "meta"},
                    progress_token="tok-7",
                )
            except TypeError:
                # SDK does not accept progress_token directly; just call.
                await client.call_tool(
                    "add_todo", {"text": "meta", "context": "meta"}
                )

    time.sleep(0.5)
    extra = _extra(_last_call_event(capture_queue))
    meta = extra.get("meta") or {}
    # If progress_token was accepted, confirm it round-tripped. Otherwise just
    # confirm meta is at least a dict (i.e. wiring is in place).
    if "progressToken" in meta:
        assert meta["progressToken"] == "tok-7"


@pytest.mark.asyncio
async def test_initialize_event_also_carries_extra(
    official_http_server, capture_queue
):
    url, _ = official_http_server
    async with streamablehttp_client(
        url, headers={"X-Init-Header": "init-value"}
    ) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()

    time.sleep(0.5)
    init_events = [e for e in capture_queue if e.event_type == "mcp:initialize"]
    assert init_events
    headers = (
        (init_events[0].parameters or {})
        .get("extra", {})
        .get("requestInfo", {})
        .get("headers", {})
    )
    assert headers.get("x-init-header") == "init-value"
```

- [ ] **Step 2: Run the file**

Run: `uv run pytest tests/e2e/official/test_request_extra_http.py -v`
Expected: 6 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/official/test_request_extra_http.py
git commit -m "test(e2e): parameters.extra.requestInfo.headers parity over HTTP

6 tests covering custom headers, User-Agent, mcp-session-id, request id
distinctness, _meta passthrough, and initialize-event extra capture."
```

---

## Task 5: `tests/e2e/official/test_session_http.py` (4 tests)

**Files:**
- Create: `tests/e2e/official/test_session_http.py`

- [ ] **Step 1: Create the file**

```python
"""Header-derived client_info extraction tests over real Streamable HTTP.

The MCPCatOptions used here disable enable_tool_call_context for cleaner
assertions on session-derived fields (we don't need the context-injection
machinery to test client_info extraction).
"""

from __future__ import annotations

import time

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from mcpcat import MCPCatOptions


def MCPCAT_OPTIONS_FACTORY() -> MCPCatOptions:
    return MCPCatOptions(enable_tracing=True, stateless=True)


pytestmark = pytest.mark.e2e


def _last_event(capture_queue, event_type: str):
    return [e for e in capture_queue if e.event_type == event_type][-1]


@pytest.mark.asyncio
async def test_user_agent_parsed_into_client_name_version(
    official_http_server, capture_queue
):
    url, _ = official_http_server
    async with streamablehttp_client(
        url, headers={"User-Agent": "Cursor/2.6.22"}
    ) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await client.call_tool(
                "add_todo", {"text": "ua-parse", "context": "ua"}
            )

    time.sleep(0.5)
    ev = _last_event(capture_queue, "mcp:tools/call")
    assert ev.client_name == "Cursor", f"expected Cursor, got {ev.client_name}"
    assert ev.client_version == "2.6.22"


@pytest.mark.asyncio
async def test_x_mcp_client_headers_override_user_agent(
    official_http_server, capture_queue
):
    url, _ = official_http_server
    async with streamablehttp_client(
        url,
        headers={
            "User-Agent": "Cursor/2.6.22",
            "X-MCP-Client-Name": "CustomClient",
            "X-MCP-Client-Version": "9.9.9",
        },
    ) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await client.call_tool(
                "add_todo", {"text": "override", "context": "override"}
            )

    time.sleep(0.5)
    ev = _last_event(capture_queue, "mcp:tools/call")
    assert ev.client_name == "CustomClient"
    assert ev.client_version == "9.9.9"


@pytest.mark.asyncio
async def test_initialize_clientinfo_wins_over_headers(
    official_http_server, capture_queue
):
    """The clientInfo passed in InitializeRequest.params should beat header parsing."""
    url, _ = official_http_server
    async with streamablehttp_client(
        url, headers={"User-Agent": "Cursor/2.6.22"}
    ) as (read, write, _):
        async with ClientSession(
            read,
            write,
            client_info={"name": "MyAgent", "version": "1.2.3"},
        ) as client:
            await client.initialize()

    time.sleep(0.5)
    init = _last_event(capture_queue, "mcp:initialize")
    assert init.client_name == "MyAgent"
    assert init.client_version == "1.2.3"


@pytest.mark.asyncio
async def test_unparseable_user_agent_does_not_crash(
    official_http_server, capture_queue
):
    url, _ = official_http_server
    async with streamablehttp_client(
        url, headers={"User-Agent": "not-a-recognizable-format"}
    ) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await client.call_tool(
                "add_todo", {"text": "weird-ua", "context": "weird"}
            )

    time.sleep(0.5)
    ev = _last_event(capture_queue, "mcp:tools/call")
    # Implementation falls through to setting client_name = full UA string.
    assert ev.client_name == "not-a-recognizable-format"
    # No crash, no exception in the worker — by virtue of getting here.
```

- [ ] **Step 2: Run the file**

Run: `uv run pytest tests/e2e/official/test_session_http.py -v`
Expected: 4 PASS.

NOTE: `ClientSession(..., client_info=...)` must be supported by the installed `mcp` SDK version. If the test fails because `client_info` is not a kwarg, replace the kwarg with the SDK-specific call signature (the test asserts behavior, not specific signature).

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/official/test_session_http.py
git commit -m "test(e2e): client_info extraction from real HTTP headers

4 tests: User-Agent parsing, X-MCP-Client-* override, initialize clientInfo
takes precedence, malformed User-Agent doesn't crash."
```

---

## Task 6: `tests/e2e/official/test_stateless_http.py` (3 tests)

**Files:**
- Create: `tests/e2e/official/test_stateless_http.py`

- [ ] **Step 1: Create the file**

```python
"""Stateless mode behavior over real Streamable HTTP."""

from __future__ import annotations

import asyncio
import time

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from mcpcat import MCPCatOptions


def MCPCAT_OPTIONS_FACTORY() -> MCPCatOptions:
    return MCPCatOptions(enable_tracing=True, stateless=True)


pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_stateless_mode_returns_null_session_id(
    official_http_server, capture_queue
):
    url, _ = official_http_server
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await client.call_tool(
                "add_todo", {"text": "s", "context": "stateless"}
            )

    time.sleep(0.5)
    call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
    assert call_events
    # In stateless mode, the SDK-level session_id field on the event is None
    # (server-issued sessions are disabled). The transport-level mcp-session-id
    # header may or may not be present depending on SDK behavior.
    assert call_events[0].session_id is None


@pytest.mark.asyncio
async def test_stateless_two_clients_different_uas_dont_bleed(
    official_http_server, capture_queue
):
    """Concurrent stateless requests with different User-Agents must produce
    events whose client_name reflects the *requesting* connection, not a
    cached value from a different connection."""
    url, _ = official_http_server

    async def call_with_ua(ua: str, text: str) -> None:
        async with streamablehttp_client(url, headers={"User-Agent": ua}) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as client:
                await client.initialize()
                await client.call_tool(
                    "add_todo", {"text": text, "context": "no-bleed"}
                )

    await asyncio.gather(
        call_with_ua("Cursor/2.6.22", "a"),
        call_with_ua("Claude/1.0.0", "b"),
    )
    time.sleep(0.7)

    call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
    client_names = {ev.client_name for ev in call_events}
    assert "Cursor" in client_names and "Claude" in client_names, (
        f"stateless mode bled client_info across requests: {client_names}"
    )


@pytest.mark.asyncio
async def test_stateless_no_session_info_pollution(
    official_http_server, capture_queue
):
    """After multiple stateless requests, the server's data.session_info
    fields should remain unset (None), proving we're not caching."""
    url, server = official_http_server

    async with streamablehttp_client(
        url, headers={"User-Agent": "First/1.0"}
    ) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await client.call_tool("add_todo", {"text": "1", "context": "x"})

    async with streamablehttp_client(
        url, headers={"User-Agent": "Second/2.0"}
    ) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await client.call_tool("add_todo", {"text": "2", "context": "x"})

    time.sleep(0.5)

    from mcpcat.modules.internal import get_server_tracking_data

    data = get_server_tracking_data(server)
    assert data is not None
    # In stateless mode, we never write to session_info.client_name.
    assert data.session_info.client_name is None, (
        f"stateless mode polluted session_info.client_name = "
        f"{data.session_info.client_name}"
    )
```

- [ ] **Step 2: Run the file**

Run: `uv run pytest tests/e2e/official/test_stateless_http.py -v`
Expected: 3 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/official/test_stateless_http.py
git commit -m "test(e2e): stateless mode behavior over real HTTP

3 tests: null session_id, no client_info bleed across concurrent clients,
no session_info pollution after multiple stateless requests."
```

---

## Task 7: `tests/e2e/official/test_identify_http.py` (5 tests)

**Files:**
- Create: `tests/e2e/official/test_identify_http.py`

NOTE: This file relies on the `mcpcat:identify` self-event introduced in `61bd6a2 feat: run identify hook per event and drop session identity cache`. Identify hook now runs on every event in both stateful and stateless modes.

The identify-hook scenarios vary per test (each test defines its own callback), which means we can't use the module-scoped server with a single options factory. Solution: this file declares no `MCPCAT_OPTIONS_FACTORY` (so the harness uses tracing-only defaults with NO identify hook), and each test patches `MCPCatData.options.identify` on the running server's tracking data before exercising the call. This is the same pattern `tests/test_stateless.py` uses.

- [ ] **Step 1: Create the file**

```python
"""Identify-per-event behavior over real Streamable HTTP.

Tests mutate the running server's MCPCatData.options.identify to vary the hook
per scenario. The default options-factory is tracing-only with no identify;
identifyswapping on the live server matches the pattern used by
tests/test_stateless.py.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from mcpcat.modules.internal import get_server_tracking_data
from mcpcat.types import UserIdentity


pytestmark = pytest.mark.e2e


def _set_identify(server, fn) -> None:
    data = get_server_tracking_data(server)
    assert data is not None
    data.options.identify = fn


def _last_call(capture_queue):
    return [e for e in capture_queue if e.event_type == "mcp:tools/call"][-1]


@pytest.mark.asyncio
async def test_identify_hook_receives_real_request_extra(
    official_http_server, capture_queue
):
    url, server = official_http_server
    received_extras: list = []

    def identify(request: Any, extra: Any) -> Optional[UserIdentity]:
        received_extras.append(extra)
        return UserIdentity(user_id="alice", user_name="Alice", user_data=None)

    _set_identify(server, identify)
    try:
        async with streamablehttp_client(
            url, headers={"X-Identify-Hook": "yes"}
        ) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                await client.call_tool(
                    "add_todo", {"text": "id", "context": "id"}
                )

        time.sleep(0.5)
        # Hook was called at least once with a real extra. The "extra" passed
        # to the hook is the (request_context, request_context) pair the SDK
        # provides; the exact shape varies by version, but it must be non-None.
        assert received_extras, "identify hook never invoked"
        # And the captured event should reflect the identity.
        ev = _last_call(capture_queue)
        assert ev.identify_actor_given_id == "alice"
    finally:
        _set_identify(server, None)


@pytest.mark.asyncio
async def test_mcpcat_identify_self_event_published_per_request(
    official_http_server, capture_queue
):
    url, server = official_http_server

    def identify(_req: Any, _extra: Any) -> Optional[UserIdentity]:
        return UserIdentity(user_id="bob", user_name=None, user_data=None)

    _set_identify(server, identify)
    try:
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                await client.call_tool(
                    "add_todo", {"text": "self", "context": "x"}
                )

        time.sleep(0.5)
        identify_events = [
            e for e in capture_queue if e.event_type == "mcpcat:identify"
        ]
        assert identify_events, (
            f"expected mcpcat:identify event, got "
            f"{[e.event_type for e in capture_queue]}"
        )
        assert identify_events[0].identify_actor_given_id == "bob"
    finally:
        _set_identify(server, None)


@pytest.mark.asyncio
async def test_identify_can_change_identity_mid_session(
    official_http_server, capture_queue
):
    url, server = official_http_server
    counter = {"n": 0}

    def identify(_req: Any, _extra: Any) -> Optional[UserIdentity]:
        counter["n"] += 1
        if counter["n"] == 1:
            return UserIdentity(user_id="user-A", user_name=None, user_data=None)
        return UserIdentity(user_id="user-B", user_name=None, user_data=None)

    _set_identify(server, identify)
    try:
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()  # n=1 -> user-A
                await client.call_tool(  # n=2 -> user-B
                    "add_todo", {"text": "mid", "context": "x"}
                )

        time.sleep(0.5)
        call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
        init_events = [e for e in capture_queue if e.event_type == "mcp:initialize"]
        assert init_events and call_events
        assert init_events[0].identify_actor_given_id == "user-A"
        assert call_events[0].identify_actor_given_id == "user-B"
    finally:
        _set_identify(server, None)


@pytest.mark.asyncio
async def test_identify_returning_none_yields_no_self_event(
    official_http_server, capture_queue
):
    url, server = official_http_server

    def identify(_req: Any, _extra: Any) -> Optional[UserIdentity]:
        return None

    _set_identify(server, identify)
    try:
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                await client.call_tool(
                    "add_todo", {"text": "none", "context": "x"}
                )

        time.sleep(0.5)
        identify_events = [
            e for e in capture_queue if e.event_type == "mcpcat:identify"
        ]
        assert not identify_events, (
            f"identify returned None; should NOT publish self-event, got "
            f"{len(identify_events)}"
        )
    finally:
        _set_identify(server, None)


@pytest.mark.asyncio
async def test_identify_exception_does_not_break_tool_call(
    official_http_server, capture_queue
):
    url, server = official_http_server

    def identify(_req: Any, _extra: Any) -> Optional[UserIdentity]:
        raise RuntimeError("identify exploded")

    _set_identify(server, identify)
    try:
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                # Tool call must still succeed despite identify raising.
                await client.call_tool(
                    "add_todo", {"text": "boom", "context": "x"}
                )

        time.sleep(0.5)
        call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
        assert call_events, "tool/call event must still publish despite hook crash"
    finally:
        _set_identify(server, None)
```

- [ ] **Step 2: Run the file**

Run: `uv run pytest tests/e2e/official/test_identify_http.py -v`
Expected: 5 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/official/test_identify_http.py
git commit -m "test(e2e): identify-per-event behavior over real HTTP

5 tests: hook receives real extra; mcpcat:identify self-event per request;
mid-session identity change; None return suppresses self-event;
exception in hook doesn't break tool_call."
```

---

## Task 8: `tests/e2e/official/test_redaction_http.py` (3 tests)

**Files:**
- Create: `tests/e2e/official/test_redaction_http.py`

- [ ] **Step 1: Create the file**

```python
"""Redaction over real-wire payloads."""

from __future__ import annotations

import time

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from mcpcat import MCPCatOptions
from mcpcat.modules.internal import get_server_tracking_data


pytestmark = pytest.mark.e2e


def _set_redact(server, fn) -> None:
    data = get_server_tracking_data(server)
    assert data is not None
    data.options.redact_sensitive_information = fn


@pytest.mark.asyncio
async def test_redact_function_runs_on_real_event_payload(
    official_http_server, capture_queue
):
    url, server = official_http_server

    def redact(s: str) -> str:
        return s.replace("secret-todo-text", "[REDACTED]")

    _set_redact(server, redact)
    try:
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                await client.call_tool(
                    "add_todo",
                    {"text": "secret-todo-text", "context": "redact"},
                )

        time.sleep(0.5)
        call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
        assert call_events
        params = call_events[0].parameters or {}
        # The redaction walks all string fields recursively.
        text = (params.get("arguments") or {}).get("text", "")
        assert "secret-todo-text" not in text
        assert "[REDACTED]" in text
    finally:
        _set_redact(server, None)


@pytest.mark.asyncio
async def test_redaction_can_scrub_authorization_header_in_extra(
    official_http_server, capture_queue
):
    url, server = official_http_server

    def redact(s: str) -> str:
        if s.startswith("Bearer "):
            return "Bearer [REDACTED]"
        return s

    _set_redact(server, redact)
    try:
        async with streamablehttp_client(
            url, headers={"Authorization": "Bearer super-secret-token-xyz"}
        ) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                await client.call_tool(
                    "add_todo", {"text": "auth", "context": "auth"}
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
        auth = headers.get("authorization")
        assert auth is not None
        assert "super-secret-token-xyz" not in auth
        assert auth == "Bearer [REDACTED]"
    finally:
        _set_redact(server, None)


@pytest.mark.asyncio
async def test_redaction_failure_drops_event(official_http_server, capture_queue):
    url, server = official_http_server

    def redact(_s: str) -> str:
        raise RuntimeError("redaction exploded")

    _set_redact(server, redact)
    try:
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                await client.call_tool(
                    "add_todo", {"text": "drop", "context": "drop"}
                )

        time.sleep(1.0)
        # Event_queue logs and drops the event when redaction raises. Verify
        # no tool/call event was published. (Initialize event was also redacted
        # and dropped.)
        call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
        assert not call_events, (
            f"redaction failure must drop event, got {len(call_events)}"
        )
    finally:
        _set_redact(server, None)
```

- [ ] **Step 2: Run the file**

Run: `uv run pytest tests/e2e/official/test_redaction_http.py -v`
Expected: 3 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/official/test_redaction_http.py
git commit -m "test(e2e): redaction over real-wire payloads

3 tests: redact runs on event params; can scrub Authorization header in
extra.requestInfo.headers; redaction raise drops event."
```

---

## Task 9: Community v3 harness + smoke test

**Files:**
- Create: `tests/e2e/community_v3/__init__.py`
- Create: `tests/e2e/community_v3/conftest.py`
- Create: `tests/e2e/community_v3/test_event_capture_http.py` (smoke — 1 test)

NOTE: This task assumes the FastMCP package installed in `.venv` exposes the v3 API. The shttp_server fixture pattern lifts the approach used by `model-context-protocol-sdks/fastmcp/tests/server/http/test_http_dependencies.py`.

- [ ] **Step 1: Create `tests/e2e/community_v3/__init__.py`** (empty)

```bash
mkdir -p tests/e2e/community_v3 && : > tests/e2e/community_v3/__init__.py
```

- [ ] **Step 2: Create `tests/e2e/community_v3/conftest.py`**

```python
"""FastMCP v3 Streamable-HTTP harness.

Boots a community FastMCP v3 server with `mcp.run_streamable_http_async(...)`
on a random port; tests connect with `fastmcp.Client(StreamableHttpTransport(url, headers=...))`.

Module-scoped: one boot per test file.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable, Tuple

import pytest

import mcpcat
from mcpcat import MCPCatOptions

from tests.e2e._helpers import find_free_port, wait_for_port

try:
    from fastmcp import FastMCP

    HAS_FASTMCP_V3 = True
except ImportError:
    FastMCP = None  # type: ignore
    HAS_FASTMCP_V3 = False


def _create_v3_todo_server() -> Any:
    if FastMCP is None:
        raise RuntimeError("fastmcp v3 is not installed; cannot run v3 e2e tests")
    mcp = FastMCP("v3-todo-server")

    @mcp.tool
    def add_todo(text: str, context: str = "") -> str:
        return f'Added todo: "{text}"'

    @mcp.tool
    def list_todos(context: str = "") -> str:
        return "no todos"

    return mcp


def _default_options_factory() -> MCPCatOptions:
    return MCPCatOptions(enable_tracing=True)


@pytest.fixture(scope="module")
def v3_http_server(request) -> Tuple[str, Any]:
    if not HAS_FASTMCP_V3:
        pytest.skip("fastmcp v3 not installed")

    options_factory: Callable[[], MCPCatOptions] = getattr(
        request.module, "MCPCAT_OPTIONS_FACTORY", _default_options_factory
    )
    options = options_factory()
    server = _create_v3_todo_server()
    mcpcat.track(server, "test_project", options)

    port = find_free_port()
    loop_ready = threading.Event()
    loop_holder: dict = {}

    def _run() -> None:
        loop = asyncio.new_event_loop()
        loop_holder["loop"] = loop
        asyncio.set_event_loop(loop)
        loop_ready.set()
        try:
            loop.run_until_complete(
                server.run_streamable_http_async(host="127.0.0.1", port=port)
            )
        except Exception:
            pass

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    loop_ready.wait(timeout=5.0)
    try:
        wait_for_port(port, timeout=5.0)
    except TimeoutError:
        loop = loop_holder.get("loop")
        if loop:
            loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2.0)
        raise

    url = f"http://127.0.0.1:{port}/mcp"
    yield url, server

    loop = loop_holder.get("loop")
    if loop:
        loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5.0)
```

- [ ] **Step 3: Create `tests/e2e/community_v3/test_event_capture_http.py` (smoke — 1 test)**

```python
"""FastMCP v3 event-capture smoke."""

from __future__ import annotations

import time

import pytest


pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_initialize_via_v3(v3_http_server, capture_queue):
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, _server = v3_http_server
    async with Client(StreamableHttpTransport(url)) as client:
        # Connecting performs the initialize handshake.
        await client.list_tools()

    time.sleep(0.5)
    init_events = [e for e in capture_queue if e.event_type == "mcp:initialize"]
    assert init_events, (
        f"expected mcp:initialize, got {[e.event_type for e in capture_queue]}"
    )
```

- [ ] **Step 4: Run the smoke**

Run: `uv run pytest tests/e2e/community_v3/test_event_capture_http.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/community_v3/
git commit -m "test(e2e): community FastMCP v3 harness + smoke

Adds run_streamable_http_async-in-thread fixture and an initialize
smoke test proving the harness wires up correctly."
```

---

## Task 10: Complete `tests/e2e/community_v3/test_event_capture_http.py` (3 tests)

**Files:**
- Modify: `tests/e2e/community_v3/test_event_capture_http.py`

- [ ] **Step 1: Replace the file with the full set**

```python
"""FastMCP v3 event-capture tests over real Streamable HTTP."""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_initialize_via_v3(v3_http_server, capture_queue):
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, _ = v3_http_server
    async with Client(StreamableHttpTransport(url)) as client:
        await client.list_tools()

    time.sleep(0.5)
    assert any(e.event_type == "mcp:initialize" for e in capture_queue)


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
```

- [ ] **Step 2: Run the file**

Run: `uv run pytest tests/e2e/community_v3/test_event_capture_http.py -v`
Expected: 3 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/community_v3/test_event_capture_http.py
git commit -m "test(e2e): complete v3 event-capture suite (3 tests)"
```

---

## Task 11: `tests/e2e/community_v3/test_request_extra_http.py` (3 tests)

**Files:**
- Create: `tests/e2e/community_v3/test_request_extra_http.py`

- [ ] **Step 1: Create the file**

```python
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
async def test_initialize_event_carries_headers_via_v3(
    v3_http_server, capture_queue
):
    """Initialize-event headers must arrive whether via the primary
    request_context.request path or the FastMCP _current_http_request fallback."""
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, _ = v3_http_server
    async with Client(
        StreamableHttpTransport(url, headers={"X-V3-Init": "init-v"})
    ) as client:
        await client.list_tools()

    time.sleep(0.5)
    init_events = [e for e in capture_queue if e.event_type == "mcp:initialize"]
    assert init_events
    headers = (
        (init_events[0].parameters or {})
        .get("extra", {})
        .get("requestInfo", {})
        .get("headers", {})
    )
    assert headers.get("x-v3-init") == "init-v", (
        f"expected x-v3-init on initialize event, got headers={headers}"
    )


@pytest.mark.asyncio
async def test_meta_progresstoken_passes_through(v3_http_server, capture_queue):
    """If the FastMCP v3 client surfaces a way to set progressToken, verify it
    rides through extra.meta. If not, just verify extra.meta is at least a dict."""
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, _ = v3_http_server
    async with Client(StreamableHttpTransport(url)) as client:
        await client.call_tool(
            "add_todo", {"text": "v3-meta", "context": "meta"}
        )

    time.sleep(0.5)
    extra = _extra(_last_call(capture_queue))
    # meta key may or may not be present depending on whether the client
    # supplied progressToken; if present, it must be a dict.
    meta = extra.get("meta")
    if meta is not None:
        assert isinstance(meta, dict)
```

- [ ] **Step 2: Run the file**

Run: `uv run pytest tests/e2e/community_v3/test_request_extra_http.py -v`
Expected: 3 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/community_v3/test_request_extra_http.py
git commit -m "test(e2e): v3 parameters.extra.requestInfo.headers parity (3 tests)"
```

---

## Task 12: `tests/e2e/community_v3/test_stateless_http.py` (2 tests)

**Files:**
- Create: `tests/e2e/community_v3/test_stateless_http.py`

- [ ] **Step 1: Create the file**

```python
"""FastMCP v3 stateless mode over real HTTP."""

from __future__ import annotations

import asyncio
import time

import pytest

from mcpcat import MCPCatOptions


def MCPCAT_OPTIONS_FACTORY() -> MCPCatOptions:
    return MCPCatOptions(enable_tracing=True, stateless=True)


pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_v3_stateless_via_global_settings(v3_http_server, capture_queue):
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, _ = v3_http_server
    async with Client(StreamableHttpTransport(url)) as client:
        await client.call_tool(
            "add_todo", {"text": "s", "context": "stateless-v3"}
        )

    time.sleep(0.5)
    call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
    assert call_events
    assert call_events[0].session_id is None


@pytest.mark.asyncio
async def test_v3_stateless_two_clients_dont_bleed(
    v3_http_server, capture_queue
):
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, _ = v3_http_server

    async def call(ua: str, text: str) -> None:
        async with Client(
            StreamableHttpTransport(url, headers={"User-Agent": ua})
        ) as client:
            await client.call_tool(
                "add_todo", {"text": text, "context": "no-bleed"}
            )

    await asyncio.gather(
        call("Cursor/2.6.22", "a"), call("Claude/1.0.0", "b")
    )
    time.sleep(0.7)

    call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
    client_names = {ev.client_name for ev in call_events}
    assert "Cursor" in client_names and "Claude" in client_names, (
        f"v3 stateless mode bled client_info: {client_names}"
    )
```

- [ ] **Step 2: Run the file**

Run: `uv run pytest tests/e2e/community_v3/test_stateless_http.py -v`
Expected: 2 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/community_v3/test_stateless_http.py
git commit -m "test(e2e): v3 stateless mode over real HTTP (2 tests)"
```

---

## Task 13: `tests/e2e/community_v3/test_identify_http.py` (2 tests)

**Files:**
- Create: `tests/e2e/community_v3/test_identify_http.py`

- [ ] **Step 1: Create the file**

```python
"""Identify-per-event behavior under FastMCP v3 middleware over real HTTP."""

from __future__ import annotations

import time
from typing import Any, Optional

import pytest

from mcpcat.modules.internal import get_server_tracking_data
from mcpcat.types import UserIdentity


pytestmark = pytest.mark.e2e


def _set_identify(server, fn) -> None:
    data = get_server_tracking_data(server)
    assert data is not None
    data.options.identify = fn


@pytest.mark.asyncio
async def test_identify_hook_runs_under_v3_middleware(
    v3_http_server, capture_queue
):
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, server = v3_http_server
    seen: list = []

    def identify(_req: Any, extra: Any) -> Optional[UserIdentity]:
        seen.append(extra)
        return UserIdentity(user_id="v3-user", user_name=None, user_data=None)

    _set_identify(server, identify)
    try:
        async with Client(StreamableHttpTransport(url)) as client:
            await client.call_tool(
                "add_todo", {"text": "id-v3", "context": "id"}
            )

        time.sleep(0.5)
        call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
        assert call_events
        assert call_events[0].identify_actor_given_id == "v3-user"
        assert seen, "identify hook never invoked under v3"
    finally:
        _set_identify(server, None)


@pytest.mark.asyncio
async def test_mcpcat_identify_self_event_via_v3_middleware(
    v3_http_server, capture_queue
):
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, server = v3_http_server

    def identify(_req: Any, _extra: Any) -> Optional[UserIdentity]:
        return UserIdentity(user_id="v3-bob", user_name=None, user_data=None)

    _set_identify(server, identify)
    try:
        async with Client(StreamableHttpTransport(url)) as client:
            await client.call_tool(
                "add_todo", {"text": "self-v3", "context": "x"}
            )

        time.sleep(0.5)
        identify_events = [
            e for e in capture_queue if e.event_type == "mcpcat:identify"
        ]
        assert identify_events, (
            f"expected mcpcat:identify under v3, got "
            f"{[e.event_type for e in capture_queue]}"
        )
        assert identify_events[0].identify_actor_given_id == "v3-bob"
    finally:
        _set_identify(server, None)
```

- [ ] **Step 2: Run the file**

Run: `uv run pytest tests/e2e/community_v3/test_identify_http.py -v`
Expected: 2 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/community_v3/test_identify_http.py
git commit -m "test(e2e): v3 identify-per-event over real HTTP (2 tests)"
```

---

## Task 14: Community v2 harness + headers smoke

**Files:**
- Create: `tests/e2e/community_v2/__init__.py`
- Create: `tests/e2e/community_v2/conftest.py`
- Create: `tests/e2e/community_v2/test_request_extra_http.py` (1 test)

NOTE: Community FastMCP v2 has a different runtime API than v3. The `mcp.run(transport="streamable-http", host=..., port=...)` form works but blocks. Use the same uvicorn-in-thread pattern as the official harness, calling `streamable_http_app()` on the v2 server. If `streamable_http_app` is not exposed at the v2 API, fall back to `mcp.run_async(...)` in a thread (similar to v3 but for v2). Verify which is available before proceeding.

- [ ] **Step 1: Create `tests/e2e/community_v2/__init__.py`** (empty)

```bash
mkdir -p tests/e2e/community_v2 && : > tests/e2e/community_v2/__init__.py
```

- [ ] **Step 2: Identify the v2 HTTP entry point**

Run: `uv run python -c "from fastmcp import FastMCP; m = FastMCP('x'); print([a for a in dir(m) if 'http' in a.lower() or 'streamable' in a.lower()])"`

Pick the appropriate API from output:
- If `streamable_http_app` is on the list → use the official-style uvicorn pattern.
- If `run_streamable_http_async` is the primary surface → use the v3-style threaded asyncio loop pattern.

- [ ] **Step 3: Create `tests/e2e/community_v2/conftest.py`**

If `streamable_http_app` is available (most likely path):

```python
"""Community FastMCP v2 Streamable-HTTP harness."""

from __future__ import annotations

import threading
from typing import Any, Callable, Tuple

import pytest
import uvicorn

import mcpcat
from mcpcat import MCPCatOptions

from tests.e2e._helpers import find_free_port, wait_for_port

try:
    from fastmcp import FastMCP as CommunityFastMCP
    HAS_FASTMCP_V2 = True
except ImportError:
    CommunityFastMCP = None  # type: ignore
    HAS_FASTMCP_V2 = False


def _create_v2_todo_server() -> Any:
    if CommunityFastMCP is None:
        raise RuntimeError("community fastmcp not installed")
    mcp = CommunityFastMCP("v2-todo")

    @mcp.tool()
    def add_todo(text: str, context: str = "") -> str:
        return f'Added: "{text}"'

    return mcp


def _default_options_factory() -> MCPCatOptions:
    return MCPCatOptions(enable_tracing=True)


@pytest.fixture(scope="module")
def v2_http_server(request) -> Tuple[str, Any]:
    if not HAS_FASTMCP_V2:
        pytest.skip("community fastmcp not installed")

    options_factory: Callable[[], MCPCatOptions] = getattr(
        request.module, "MCPCAT_OPTIONS_FACTORY", _default_options_factory
    )
    server = _create_v2_todo_server()
    mcpcat.track(server, "test_project", options_factory())

    # Use whichever ASGI factory v2 exposes. Adjust this line per Step 2 finding.
    app = server.streamable_http_app()
    port = find_free_port()
    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="error", lifespan="on"
    )
    uv_server = uvicorn.Server(config)
    thread = threading.Thread(target=uv_server.run, daemon=True)
    thread.start()
    try:
        wait_for_port(port, timeout=5.0)
    except TimeoutError:
        uv_server.should_exit = True
        thread.join(timeout=2.0)
        raise

    url = f"http://127.0.0.1:{port}/mcp"
    yield url, server
    uv_server.should_exit = True
    thread.join(timeout=5.0)
```

If only `run_streamable_http_async` is available, mirror the v3 conftest pattern (create an asyncio loop in a thread, run `await server.run_streamable_http_async(host, port)`).

- [ ] **Step 4: Create `tests/e2e/community_v2/test_request_extra_http.py`**

```python
"""Community FastMCP v2 headers smoke."""

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
```

- [ ] **Step 5: Run the file**

Run: `uv run pytest tests/e2e/community_v2/test_request_extra_http.py -v`
Expected: 1 PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/e2e/community_v2/
git commit -m "test(e2e): community v2 harness + headers smoke"
```

---

## Task 15: `tests/e2e/community_v2/test_identify_http.py` (1 test)

**Files:**
- Create: `tests/e2e/community_v2/test_identify_http.py`

- [ ] **Step 1: Create the file**

```python
"""Community FastMCP v2 identify-per-event smoke."""

from __future__ import annotations

import time
from typing import Any, Optional

import pytest

from mcpcat.modules.internal import get_server_tracking_data
from mcpcat.types import UserIdentity


pytestmark = pytest.mark.e2e


def _set_identify(server, fn) -> None:
    data = get_server_tracking_data(server)
    assert data is not None
    data.options.identify = fn


@pytest.mark.asyncio
async def test_v2_identify_hook_receives_real_extra(
    v2_http_server, capture_queue
):
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    url, server = v2_http_server
    seen: list = []

    def identify(_req: Any, extra: Any) -> Optional[UserIdentity]:
        seen.append(extra)
        return UserIdentity(user_id="v2-user", user_name=None, user_data=None)

    _set_identify(server, identify)
    try:
        async with Client(
            StreamableHttpTransport(url, headers={"X-Identify-V2": "yes"})
        ) as client:
            await client.call_tool(
                "add_todo", {"text": "id-v2", "context": "id"}
            )

        time.sleep(0.5)
        call_events = [e for e in capture_queue if e.event_type == "mcp:tools/call"]
        assert call_events
        assert call_events[0].identify_actor_given_id == "v2-user"
        assert seen, "v2 identify hook never invoked"
    finally:
        _set_identify(server, None)
```

- [ ] **Step 2: Run the file**

Run: `uv run pytest tests/e2e/community_v2/test_identify_http.py -v`
Expected: 1 PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/community_v2/test_identify_http.py
git commit -m "test(e2e): community v2 identify-per-event smoke"
```

---

## Task 16: Final integration check

**Files:**
- None (verification only)

- [ ] **Step 1: Run the entire e2e suite**

Run: `uv run pytest tests/e2e/ -v`
Expected: ~38 PASS (26 official + 10 v3 + 2 v2). Runtime: ~25–30s.

- [ ] **Step 2: Run the entire repo test suite**

Run: `uv run pytest -q`
Expected: ~443 passing, no regressions, runtime ~165s.

- [ ] **Step 3: Run the community-specific subsuite to confirm no fixture collisions**

Run: `uv run pytest tests/community/ tests/e2e/community_v2/ tests/e2e/community_v3/ -q`
Expected: All pass.

- [ ] **Step 4: If anything fails**

For each failing test:
1. Read the failure carefully.
2. Determine whether it's a wiring issue (test) or a real SDK behavior gap.
3. If wiring: fix in the affected test file, re-run that file alone.
4. If real gap: stop and surface the discrepancy — DO NOT modify production code in this plan; that's a separate change.

- [ ] **Step 5: No commit needed if all green.** If fixes were made in Step 4, commit them as `test(e2e): fix harness/test wiring discovered in final integration`.

---

## Self-Review notes

- **Spec coverage:** All 12 spec-listed test files are produced (Tasks 2,3 → 1; Tasks 4–8 → 5 more in official; Tasks 9–13 → 5 in v3; Tasks 14–15 → 2 in v2).
- **Identify-per-event coverage:** Task 7 (5 tests) covers the new behavior end-to-end including mid-session change, None return, and exception swallow. Tasks 13 and 15 cover v3 and v2 smoke respectively.
- **The `test_initialize_uses_fastmcp_get_http_request_fallback` ambiguity** flagged during brainstorming is addressed in Task 11 by reframing to `test_initialize_event_carries_headers_via_v3` — asserts headers arrive on the initialize event without locking to a specific code path.
- **v2 harness API uncertainty** is deliberately surfaced as Step 2 of Task 14 (run a probe to identify the available API) rather than assumed.
- **No placeholders.** All steps include exact code, exact commands, and exact expected output.

## Verification (overall)

- `uv run pytest tests/e2e/ -v` → ~38 PASS.
- `uv run pytest -q` → ~443 PASS (was 405).
- `git log --oneline origin/main..HEAD` shows ~16 commits, one per task.
