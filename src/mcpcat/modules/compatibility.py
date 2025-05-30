"""Compatibility checks for MCP servers."""

from typing import Any, Protocol, runtime_checkable

from mcp import ServerResult


@runtime_checkable
class MCPServerProtocol(Protocol):
    """Protocol for MCP server compatibility."""

    def list_tools(self) -> Any:
        """List available tools."""
        ...

    def call_tool(self, name: str, arguments: dict) -> Any:
        """Call a tool by name."""
        ...


def is_fastmcp_server(server: Any) -> bool:
    """Check if the server is a FastMCP instance."""
    # Check for FastMCP class name or specific attributes
    return hasattr(server, "_mcp_server")

def has_neccessary_attributes(server: Any) -> bool:
    """Check if the server has necessary attributes for compatibility."""
    required_methods = ["list_tools", "call_tool"]
    
    # Check for core methods that both FastMCP and Server implementations have
    for method in required_methods:
        if not hasattr(server, method):
            return False
    
    # For FastMCP servers, verify internal MCP server exists
    if hasattr(server, "_mcp_server"):
        # FastMCP server - check that internal MCP server has request_context
        # Use dir() to avoid triggering property getters that might raise exceptions
        if "request_context" not in dir(server._mcp_server):
            return False
        # Check for get_context method which is FastMCP specific
        if not hasattr(server, "get_context"):
            return False
        # Check for request_handlers dictionary on internal server
        if not hasattr(server._mcp_server, "request_handlers"):
            return False
        if not isinstance(server._mcp_server.request_handlers, dict):
            return False
    else:
        # Regular Server implementation - check for request_context directly
        # Use dir() to avoid triggering property getters that might raise exceptions
        if "request_context" not in dir(server):
            return False
        # Check for request_handlers dictionary
        if not hasattr(server, "request_handlers"):
            return False
        if not isinstance(server.request_handlers, dict):
            return False
    
    return True


def is_compatible_server(server: Any) -> bool:
    """Check if the server is compatible with MCPCat."""
    return has_neccessary_attributes(server)


def get_mcp_compatible_error_message(error: Any) -> str:
    """Get error message in a compatible format."""
    if isinstance(error, Exception):
        return str(error)
    return str(error)

def is_mcp_error_response(response: ServerResult) -> tuple[bool, str]:
    """Check if the response is an MCP error."""
    try:
        # ServerResult is a RootModel, so we need to access its root attribute
        if hasattr(response, 'root'):
            result = response.root
            # Check if it's a CallToolResult with an error
            if hasattr(result, 'isError') and result.isError:
                # Extract error message from content
                if hasattr(result, 'content') and result.content:
                    # content is a list of TextContent/ImageContent/EmbeddedResource
                    for content_item in result.content:
                        # Check if it has a text attribute (TextContent)
                        if hasattr(content_item, 'text'):
                            return True, str(content_item.text)
                        # Check if it has type and content attributes
                        elif hasattr(content_item, 'type') and hasattr(content_item, 'content'):
                            if content_item.type == 'text':
                                return True, str(content_item.content)
                    
                    # If no text content found, stringify the first item
                    if result.content and len(result.content) > 0:
                        return True, str(result.content[0])
                    return True, "Unknown error"
                return True, "Unknown error"
        return False, ""
    except (AttributeError, IndexError):
        # Handle specific exceptions more precisely
        return False, ""
    except Exception as e:
        # Log unexpected errors but still return a valid response
        return False, f"Error checking response: {str(e)}"