"""Community FastMCP todo server implementation for testing."""

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from fastmcp import FastMCP

try:
    from fastmcp import FastMCP as CommunityFastMCP
    HAS_COMMUNITY_FASTMCP = True
except ImportError:
    CommunityFastMCP = None  # type: ignore
    HAS_COMMUNITY_FASTMCP = False


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

    # Store original handlers for testing (community FastMCP doesn't expose them the same way)
    # but we can access the tools through the server's tool manager
    # Using setattr to avoid type checking issues with dynamic attributes
    setattr(
        server,
        "_original_handlers",
        {
            "add_todo": add_todo,
            "list_todos": list_todos,
            "complete_todo": complete_todo,
        },
    )

    return server