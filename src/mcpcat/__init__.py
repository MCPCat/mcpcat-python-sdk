"""MCPCat - Analytics Tool for MCP Servers."""

from datetime import datetime, timezone
from typing import Any

from mcpcat.modules.overrides.mcp_server import override_lowlevel_mcp_server
from mcpcat.modules.session import (
    get_session_info,
    new_session_id,
)

from .modules.compatibility import is_compatible_server, is_fastmcp_server
from .modules.internal import set_server_tracking_data
from .modules.logging import write_to_log
from .types import (
    MCPCatData,
    MCPCatOptions,
    UserIdentity,
    IdentifyFunction,
    RedactionFunction,
)


def track(server: Any, project_id: str, options: MCPCatOptions | None = None) -> Any:
    # Use default options if not provided
    if options is None:
        options = MCPCatOptions()

    # Validate server compatibility
    if not is_compatible_server(server):
        raise TypeError(
            "Server must be a FastMCP instance or MCP Low-level Server instance"
        )

    lowlevel_server = server
    if is_fastmcp_server(server):
        lowlevel_server = server._mcp_server

    # Create and store tracking data
    session_id = new_session_id()
    session_info = get_session_info(lowlevel_server)
    data = MCPCatData(
        session_id=session_id,
        project_id=project_id,
        last_activity=datetime.now(timezone.utc),
        session_info=session_info,
        identified_sessions=dict(),
        options=options,
    )
    set_server_tracking_data(lowlevel_server, data)

    try:
        override_lowlevel_mcp_server(lowlevel_server, data)
        write_to_log(f"MCPCat initialized for sessions {session_id} on project {project_id}")
    except Exception as e:
        write_to_log(f"Error initializing MCPCat: {e}")
    return server

__all__ = [
    # Main API
    "track",
    # Configuration
    "MCPCatOptions",
    # Types for identify functionality
    "UserIdentity",
    "IdentifyFunction",
    # Type for redaction functionality
    "RedactionFunction",
]
