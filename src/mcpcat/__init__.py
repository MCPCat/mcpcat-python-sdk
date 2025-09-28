"""MCPCat - Analytics Tool for MCP Servers."""

from datetime import datetime, timezone
from typing import Any

from mcpcat.modules.overrides.mcp_server import override_lowlevel_mcp_server
from mcpcat.modules.session import (
    get_session_info,
    new_session_id,
)

from .modules.compatibility import (
    is_community_fastmcp_server,
    is_compatible_server,
    is_official_fastmcp_server,
    COMPATIBILITY_ERROR_MESSAGE,
)
from .modules.internal import set_server_tracking_data
from .modules.logging import write_to_log, set_debug_mode
from .types import (
    MCPCatData,
    MCPCatOptions,
    UserIdentity,
    IdentifyFunction,
    RedactionFunction,
)


def track(
    server: Any, project_id: str | None = None, options: MCPCatOptions | None = None
) -> Any:
    """
    Initialize MCPCat tracking with optional telemetry export.

    Args:
        server: MCP server instance to track
        project_id: MCPCat project ID (optional if using telemetry-only mode)
        options: Configuration options including telemetry exporters

    Returns:
        The server instance with tracking enabled

    Raises:
        ValueError: If neither project_id nor exporters are provided
        TypeError: If server is not a compatible MCP server instance
    """
    # Use default options if not provided
    if options is None:
        options = MCPCatOptions()

    # Update global debug_mode value
    set_debug_mode(options.debug_mode)

    # Validate configuration
    if not project_id and not options.exporters:
        raise ValueError(
            "Either project_id or exporters must be provided. "
            "Use project_id for MCPCat, exporters for telemetry-only mode, or both."
        )

    # Validate server compatibility
    if not is_compatible_server(server):
        raise TypeError(COMPATIBILITY_ERROR_MESSAGE)

    lowlevel_server = server
    is_fastmcp = is_official_fastmcp_server(server) or is_community_fastmcp_server(server)
    is_official_fastmcp = is_official_fastmcp_server(server)
    is_community_fastmcp = is_community_fastmcp_server(server)

    if is_fastmcp:
        lowlevel_server = server._mcp_server

    # Initialize telemetry if exporters configured
    if options.exporters:
        from mcpcat.modules.telemetry import TelemetryManager
        from mcpcat.modules.event_queue import set_telemetry_manager

        telemetry_manager = TelemetryManager(options.exporters)
        set_telemetry_manager(telemetry_manager)
        write_to_log(f"Telemetry initialized with {len(options.exporters)} exporter(s)")

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
        from mcpcat.modules.overrides.official.monkey_patch import apply_official_fastmcp_patches

        # Initialize the dynamic tracking system by setting the flag
        if not data.tracker_initialized:
            data.tracker_initialized = True
            write_to_log(
                f"Dynamic tracking initialized for server {id(lowlevel_server)}"
            )

        # Apply appropriate tracking method based on server type
        if is_official_fastmcp:
            # For FastMCP servers, use monkey-patching for tool tracking
            apply_official_fastmcp_patches(server, data)
            # Only apply minimal overrides for non-tool events (like initialize, list_tools display)
            from mcpcat.modules.overrides.mcp_server import (
                override_lowlevel_mcp_server_minimal,
            )

            override_lowlevel_mcp_server_minimal(lowlevel_server, data)
        elif is_community_fastmcp:
            # For community FastMCP servers, use community-specific patches
            from mcpcat.modules.overrides.community.monkey_patch import patch_community_fastmcp
            patch_community_fastmcp(server)
            write_to_log(f"Applied community FastMCP patches for server {id(server)}")
        else:
            # For low-level servers, use the traditional overrides (no monkey patching needed)
            override_lowlevel_mcp_server(lowlevel_server, data)

        if project_id:
            write_to_log(
                f"MCPCat initialized with dynamic tracking for session {session_id} on project {project_id}"
            )
        else:
            write_to_log(
                f"MCPCat initialized in telemetry-only mode for session {session_id}"
            )

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
