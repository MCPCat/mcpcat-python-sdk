"""Community FastMCP todo server implementation for testing."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP

try:
    from fastmcp import FastMCP as CommunityFastMCP

    HAS_COMMUNITY_FASTMCP = True

    # Detect FastMCP version
    import fastmcp

    _version = getattr(fastmcp, "__version__", "0.0.0")
    # v3 starts at 3.0.0
    IS_FASTMCP_V3 = int(_version.split(".")[0]) >= 3
except ImportError:
    CommunityFastMCP = None  # type: ignore
    HAS_COMMUNITY_FASTMCP = False
    IS_FASTMCP_V3 = False


def get_lowlevel_server(server: Any) -> Any:
    """Get the low-level server for tracking data access.

    In v2, tracking data is stored on server._mcp_server.
    In v3, tracking data is stored on the server itself.

    Args:
        server: FastMCP server instance

    Returns:
        The server object where tracking data is stored
    """
    if IS_FASTMCP_V3:
        return server
    return getattr(server, "_mcp_server", server)


async def get_server_tools(server: Any) -> dict[str, Any]:
    """Get tools from the server in a version-agnostic way.

    Args:
        server: FastMCP server instance

    Returns:
        Dict mapping tool names to tool definitions
    """
    if IS_FASTMCP_V3:
        # v3: list_tools() returns a list of Tool objects
        tools_list = await server.list_tools()
        return {t.name: t for t in tools_list}
    # v2: get_tools() returns a dict
    return await server.get_tools()


class Todo:
    """Todo item."""

    def __init__(self, id: int, text: str, completed: bool = False):
        self.id = id
        self.text = text
        self.completed = completed


def create_community_todo_server() -> "FastMCP":
    """Create a todo server using community FastMCP for testing.

    Returns:
        FastMCP: A community FastMCP server instance configured as a todo server
    """
    if CommunityFastMCP is None:
        raise ImportError(
            "Community FastMCP is not available. Install it with: pip install fastmcp"
        )

    server = CommunityFastMCP("todo-server")

    todos: list[Todo] = []
    next_id = 1

    @server.tool
    def add_todo(text: str) -> str:
        """Add a new todo item."""
        nonlocal next_id
        todo = Todo(next_id, text)
        todos.append(todo)
        next_id += 1
        return f'Added todo: "{text}" with ID {todo.id}'

    @server.tool
    def list_todos() -> str:
        """List all todo items."""
        if not todos:
            return "No todos found"

        todo_list = []
        for todo in todos:
            status = "✓" if todo.completed else "○"
            todo_list.append(f"{todo.id}: {todo.text} {status}")

        return "\n".join(todo_list)

    @server.tool
    def complete_todo(id: int) -> str:
        """Mark a todo item as completed."""
        for todo in todos:
            if todo.id == id:
                todo.completed = True
                return f'Completed todo: "{todo.text}"'

        raise ValueError(f"Todo with ID {id} not found")

    # Store original handlers for testing
    # (community FastMCP doesn't expose them the same way)
    server._original_handlers = {
        "add_todo": add_todo,
        "list_todos": list_todos,
        "complete_todo": complete_todo,
    }

    return server
