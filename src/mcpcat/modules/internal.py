"""Internal data storage for MCPCat."""

import weakref
from typing import Any

from ..types import MCPCatData
from .compatibility import is_fastmcp_server

# WeakKeyDictionary to store data associated with server instances
_server_data_map: weakref.WeakKeyDictionary[Any, MCPCatData] = weakref.WeakKeyDictionary()


def set_server_tracking_data(server: Any, data: MCPCatData) -> None:
    """Store MCPCat data for a server instance."""
    # Always use low-level server as key
    if is_fastmcp_server(server):
        key = server._mcp_server
    else:
        key = server
    _server_data_map[key] = data


def get_server_tracking_data(server: Any) -> MCPCatData | None:
    """Retrieve MCPCat data for a server instance."""
    # Always use low-level server as key
    if is_fastmcp_server(server):
        key = server._mcp_server
    else:
        key = server
    return _server_data_map.get(key, None)
