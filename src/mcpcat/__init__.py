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
    is_fastmcp = is_fastmcp_server(server)
    if is_fastmcp:
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
        # Always initialize dynamic tracking for complete tool coverage
        from mcpcat.modules.overrides.monkey_patch import apply_monkey_patches
        
        # Initialize the dynamic tracking system by setting the flag
        if not data.tracker_initialized:
            data.tracker_initialized = True
            from mcpcat.modules.logging import write_to_log
            write_to_log(f"Dynamic tracking initialized for server {id(lowlevel_server)}")
        
        # Apply appropriate tracking method based on server type
        if is_fastmcp:
            # For FastMCP servers, use monkey-patching for tool tracking
            apply_monkey_patches(server, data)
            # Only apply minimal overrides for non-tool events (like initialize, list_tools display)
            from mcpcat.modules.overrides.mcp_server import override_lowlevel_mcp_server_minimal
            override_lowlevel_mcp_server_minimal(lowlevel_server, data)
        else:
            # For low-level servers, use the traditional overrides (no monkey patching needed)
            override_lowlevel_mcp_server(lowlevel_server, data)
        
        write_to_log(f"MCPCat initialized with dynamic tracking for session {session_id} on project {project_id}")
            
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
