"""Internal data storage for MCPCat."""

import weakref
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..types import EventType, MCPCatData, ToolRegistration, UnredactedEvent
from .compatibility import is_official_fastmcp_server
from .logging import write_to_log

# WeakKeyDictionary to store data associated with server instances
_server_data_map: weakref.WeakKeyDictionary[Any, MCPCatData] = (
    weakref.WeakKeyDictionary()
)

# Global storage for original unpatched methods (keyed by tool_manager or handler id)
# This is global because tool managers might be shared between servers
_original_methods: Dict[str, Any] = {}


def _get_server_key(server: Any) -> Any:
    """Get the canonical key for a server (handles FastMCP vs low-level)."""
    if is_official_fastmcp_server(server):
        return server._mcp_server
    return server


def set_server_tracking_data(server: Any, data: MCPCatData) -> None:
    """Store MCPCat data for a server instance."""
    key = _get_server_key(server)
    _server_data_map[key] = data


def get_server_tracking_data(server: Any) -> MCPCatData | None:
    """Retrieve MCPCat data for a server instance."""
    key = _get_server_key(server)
    return _server_data_map.get(key, None)


def reset_server_tracking_data(server: Any) -> None:
    """Reset tracking data for a specific server (mainly for testing)."""
    key = _get_server_key(server)
    if key in _server_data_map:
        del _server_data_map[key]
        write_to_log(f"Reset tracking data for server {id(key)}")


def reset_all_tracking_data() -> None:
    """Reset all server tracking data (mainly for testing)."""
    _server_data_map.clear()
    _original_methods.clear()
    write_to_log("Reset all server tracking data")



# Dynamic tracking helper methods
def register_tool(server: Any, name: str) -> None:
    """Register a tool in the server's tracking system."""
    data = get_server_tracking_data(server)
    if data and name not in data.tool_registry:
        data.tool_registry[name] = ToolRegistration(
            name=name, registered_at=datetime.now(timezone.utc)
        )
        write_to_log(f"Registered tool '{name}'")


def mark_tool_tracked(server: Any, name: str) -> None:
    """Mark a tool as being tracked by MCPCat for this server."""
    data = get_server_tracking_data(server)
    if data and name in data.tool_registry:
        data.tool_registry[name].tracked = True
        data.tool_registry[name].wrapped = True
        data.wrapped_tools.add(name)


def is_tool_tracked(server: Any, name: str) -> bool:
    """Check if a tool is already being tracked for this server."""
    data = get_server_tracking_data(server)
    return data and name in data.wrapped_tools


def get_untracked_tools(server: Any) -> List[str]:
    """Get list of tools that aren't tracked yet for this server."""
    data = get_server_tracking_data(server)
    if not data:
        return []
    return [name for name, reg in data.tool_registry.items() if not reg.tracked]


def discover_new_tools(server: Any, tools: List[Any]) -> List[str]:
    """Discover tools that weren't previously known for this server."""
    data = get_server_tracking_data(server)
    if not data:
        return []

    new_tools = []
    for tool in tools:
        if tool.name not in data.tool_registry:
            register_tool(server, tool.name)
            new_tools.append(tool.name)
    return new_tools


# Original methods storage (global, not per-server)
def store_original_method(key: str, method: Any) -> None:
    """Store an original unpatched method."""
    if key not in _original_methods:
        _original_methods[key] = method


def get_original_method(key: str) -> Optional[Any]:
    """Get an original unpatched method."""
    return _original_methods.get(key)


def get_original_methods() -> Dict[str, Any]:
    """Get the global original methods storage."""
    return _original_methods


def get_tool_timeline(server: Any) -> List[Dict[str, Any]]:
    """Get a timeline of tool registrations for debugging.

    Args:
        server: MCP server instance

    Returns:
        List of tool registration events sorted by time
    """
    data = get_server_tracking_data(server)
    if not data:
        return []
    timeline = []

    for name, reg in data.tool_registry.items():
        timeline.append(
            {
                "name": name,
                "registered_at": reg.registered_at.isoformat(),
                "tracked": reg.tracked,
                "wrapped": reg.wrapped,
            }
        )

    # Sort by registration time
    timeline.sort(key=lambda x: x["registered_at"])

    return timeline
