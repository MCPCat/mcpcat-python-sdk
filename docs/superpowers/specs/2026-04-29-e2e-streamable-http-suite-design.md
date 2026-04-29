# E2E Streamable-HTTP Test Suite — Design

## Context

The MCPCat Python SDK currently has 405 in-memory tests. All of them use either:

- The official MCP SDK's `create_connected_server_and_client_session` — in-memory `MemoryStream`-based transport.
- FastMCP's `Client(server)` direct in-memory connection.

Neither boots a real ASGI app. As a result, `request_context.request` is always `None` in tests, and code paths that depend on the Starlette `Request` (header capture, header-derived client info, stateless mode behavior, FastMCP's `_current_http_request` ContextVar fallback, the new per-event identify hook receiving real `extra`) only get tested via monkey-patched fakes.

This is brittle. Real users hit the SDK over Streamable HTTP, and we have no test coverage that exercises the actual transport. The recently merged identify-per-event change (`#30`) and the in-flight header-capture work (`feat/request-extra-headers`) both produce signal that only shows up under a real HTTP transport.

This spec defines a transport-parity test suite that covers transport-sensitive scenarios under real Streamable HTTP. The intended outcome is a `tests/e2e/` tree that runs as part of the default `pytest` invocation, gives us confidence the SDK behaves correctly under real HTTP, and grows naturally as new transport-sensitive features are added.

## Scope

**In scope (transport-sensitive scenarios):**

- Event capture for initialize / tools/list / tools/call under real HTTP framing.
- HTTP header capture into `event.parameters.extra.requestInfo.headers` (TS-parity).
- Header-derived client info extraction (User-Agent, x-mcp-client-name/version).
- Stateless mode with real per-request headers (no cross-request bleed).
- Identify hook receiving real `extra`, mid-session identity changes, `mcpcat:identify` self-events.
- Redaction over real wire payloads.
- FastMCP v3's `get_http_request()` ContextVar fallback under real transport.

**Out of scope (transport-agnostic, stays in-memory):**

- Tool-context schema injection (`inputSchema` modification).
- `get_more_tools` / `report_missing` semantics.
- Truncation / sanitization / validation pipeline transforms.
- Telemetry exporter wiring.
- Tag / property validation rules.

## Layout

```
tests/e2e/
  __init__.py
  conftest.py                  # cross-cutting capture-queue fixture
  official/                    # official MCP SDK FastMCP — full set (6 files)
    __init__.py
    conftest.py                # uvicorn-in-thread fixture, port helpers
    test_event_capture_http.py
    test_request_extra_http.py
    test_session_http.py
    test_stateless_http.py
    test_identify_http.py
    test_redaction_http.py
  community_v3/                # FastMCP v3 — full set (4 files)
    __init__.py
    conftest.py                # FastMCP-native shttp_server fixture
    test_event_capture_http.py
    test_request_extra_http.py
    test_stateless_http.py
    test_identify_http.py
  community_v2/                # FastMCP v2 — smoke only (2 files)
    __init__.py
    conftest.py                # uvicorn-in-thread for v2 server
    test_request_extra_http.py
    test_identify_http.py
```

Existing `tests/` and `tests/community/` stay as the in-memory contract. `tests/e2e/` is the additive transport-parity layer.

## Harness

### Top-level `tests/e2e/conftest.py`

A single fixture, `capture_queue`, that mocks the global event queue and yields the list that accumulates published events. Replaces the inline mock-queue idiom currently duplicated across in-memory tests.

```python
@pytest.fixture
def capture_queue():
    from mcpcat.modules.event_queue import event_queue as original
    captured: list = []
    mock = MagicMock()
    mock.publish_event = MagicMock(side_effect=lambda req: captured.append(req))
    set_event_queue(EventQueue(api_client=mock))
    yield captured
    set_event_queue(original)
```

### `tests/e2e/official/conftest.py`

Module-scoped uvicorn-in-thread fixture that boots the official SDK's Streamable-HTTP app on `127.0.0.1:<random>`:

```python
@pytest.fixture(scope="module")
def official_http_server(request):
    """Boot a Streamable-HTTP MCP server. One per module.

    Tests parametrize indirectly when they need different MCPCatOptions.
    """
    factory = getattr(request, "param", _default_official_factory)
    server, mcpcat_options = factory()
    track(server, "test_project", mcpcat_options)
    app = streamable_http_app(server._mcp_server)  # or `server` for low-level
    port = _find_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    uv = uvicorn.Server(config)
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    _wait_for_port(port, timeout=5.0)
    yield f"http://127.0.0.1:{port}/mcp", server
    uv.should_exit = True
    thread.join(timeout=5.0)
```

Tests connect with `streamablehttp_client(url)`:

```python
async def test_x(official_http_server, capture_queue):
    url, server = official_http_server
    async with streamablehttp_client(url, headers={"X-Custom": "v"}) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await client.call_tool("add_todo", {"text": "hi"})
    assert any("x-custom" in (e.parameters or {}).get("extra", {}).get("requestInfo", {}).get("headers", {}) for e in capture_queue)
```

### `tests/e2e/community_v3/conftest.py`

Lifts the `shttp_server` fixture pattern from `model-context-protocol-sdks/fastmcp/tests/server/http/test_http_dependencies.py`. Uses `mcp.run_streamable_http_async(host, port)` and `fastmcp.Client(url)` for the client.

### `tests/e2e/community_v2/conftest.py`

Same uvicorn-in-thread shape as official/, but instantiates a community v2 FastMCP server and uses its `streamable_http_app`.

### `tests/e2e/_helpers.py`

- `_find_free_port()` — bind/release on `127.0.0.1:0`.
- `_wait_for_port(port, timeout)` — poll until accepts connection or timeout raises.
- `mcp_post(url, payload, headers)` — raw httpx POST for the rare test that needs to send headers the MCP client doesn't expose.

## Test Scenarios

### `tests/e2e/official/`

**`test_event_capture_http.py`** — `test_initialize_event_captured`, `test_tools_list_event_captured`, `test_tools_call_event_captured`, `test_event_duration_is_non_zero`, `test_concurrent_clients_get_distinct_session_ids`.

**`test_request_extra_http.py`** — `test_custom_header_lands_in_request_info`, `test_user_agent_preserved`, `test_mcp_session_id_header_promoted_to_extra_session_id`, `test_request_id_present_per_call`, `test_meta_progresstoken_passes_through`, `test_initialize_event_also_carries_extra`.

**`test_session_http.py`** — `test_user_agent_parsed_into_client_name_version`, `test_x_mcp_client_headers_override_user_agent`, `test_initialize_clientinfo_wins_over_headers`, `test_unparseable_user_agent_does_not_crash`.

**`test_stateless_http.py`** — `test_stateless_mode_returns_null_session_id`, `test_stateless_two_clients_different_uas_dont_bleed`, `test_stateless_no_session_info_pollution`.

**`test_identify_http.py`** — `test_identify_hook_receives_real_request_extra`, `test_mcpcat_identify_self_event_published_per_request`, `test_identify_can_change_identity_mid_session`, `test_identify_returning_none_yields_no_self_event`, `test_identify_exception_does_not_break_tool_call`.

**`test_redaction_http.py`** — `test_redact_function_runs_on_real_event_payload`, `test_redaction_can_scrub_authorization_header_in_extra`, `test_redaction_failure_drops_event`.

### `tests/e2e/community_v3/`

**`test_event_capture_http.py`** — `test_initialize_via_v3`, `test_call_tool_via_v3`, `test_list_tools_via_v3`.

**`test_request_extra_http.py`** — `test_custom_header_lands_in_extra`, `test_initialize_event_carries_headers_via_v3` (asserts headers arrive on the initialize event under real v3 transport — covers both the primary `request_context.request` path and the `_current_http_request` ContextVar fallback, whichever the SDK happens to use), `test_meta_progresstoken_passes_through`.

**`test_stateless_http.py`** — `test_v3_stateless_via_global_settings`, `test_v3_stateless_two_clients_dont_bleed`.

**`test_identify_http.py`** — `test_identify_hook_runs_under_v3_middleware`, `test_mcpcat_identify_self_event_via_v3_middleware`.

### `tests/e2e/community_v2/`

**`test_request_extra_http.py`** — `test_v2_custom_header_lands_in_extra`.

**`test_identify_http.py`** — `test_v2_identify_hook_receives_real_extra`.

**Total: ~38 tests across 12 modules** — official (26) + community v3 (10) + community v2 (2).

## Markers and CI

- All e2e tests get `@pytest.mark.e2e`.
- `pyproject.toml` registers the marker:
  ```toml
  [tool.pytest.ini_options]
  markers = ["e2e: real HTTP transport tests"]
  ```
- The default `pytest` invocation **includes** e2e (no `-m` filter) — fast inner-loop dev still gets transport coverage.
- Estimated runtime impact: ~12 module-scoped uvicorn boots × ~1.5s = ~20s fixture overhead, plus ~38 tests × ~50ms = ~2s execution. Total e2e cost: ~25s on top of the existing ~140s suite.

## Failure semantics

- Server-ready timeout (5s) raises a clear fixture-level error.
- Teardown does `uv.should_exit = True` then `thread.join(timeout=5.0)`; if a thread fails to die we fail teardown loudly rather than leaking.
- Tests assert event shape, not exact values where nondeterministic (timestamps, ksuid IDs).

## Dependencies

- `uvicorn` and `httpx` are transitive deps of `mcp` and `fastmcp` already.
- No new top-level dependencies required.

## Reused utilities

- `MCPCatOptions`, `track`, `mcpcat.modules.event_queue.{EventQueue, set_event_queue}` — existing public API.
- `streamable_http_app` from `mcp.server.streamable_http_manager` — official SDK ASGI factory.
- `streamablehttp_client` from `mcp.client.streamable_http` — official SDK client.
- `fastmcp.Client(url)` — community v3 client.
- The shttp_server fixture pattern in `model-context-protocol-sdks/fastmcp/tests/server/http/test_http_dependencies.py` — model for v3 conftest.

## Verification

- `uv run pytest tests/e2e/ -v` — full e2e suite (target: ~38 passing).
- `uv run pytest` (default invocation, includes e2e) — full suite (target: 405 + ~38 = ~443 passing, no regressions).
- `uv run pytest tests/e2e/official/test_request_extra_http.py -v` — header capture proven over real HTTP, replacing the monkey-patched fakery in the existing `tests/test_request_extra.py`.
- Spot-check: in `tests/e2e/community_v3/test_request_extra_http.py::test_initialize_uses_fastmcp_get_http_request_fallback`, assert that initialize-event headers are populated despite `request_context.request` being `None` — proves the `_current_http_request` ContextVar fallback works end-to-end.
