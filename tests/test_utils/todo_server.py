"""Todo server implementation for testing."""

from mcp.server import Server

try:
    from mcp.server import FastMCP
    HAS_FASTMCP = True
except ImportError:
    FastMCP = None
    HAS_FASTMCP = False


class Todo:
    """Todo item."""

    def __init__(self, id: int, text: str, completed: bool = False):
        self.id = id
        self.text = text
        self.completed = completed


def create_todo_server():
    """Create a todo server for testing."""
    if FastMCP is None:
        raise ImportError("FastMCP is not available in this MCP version. Use create_low_level_todo_server() instead.")
    # Fix deprecation warning by not passing version as kwarg
    server = FastMCP("todo-server")

    todos: list[Todo] = []
    next_id = 1

    @server.tool()
    def add_todo(text: str) -> str:
        """Add a new todo item."""
        nonlocal next_id
        todo = Todo(next_id, text)
        todos.append(todo)
        next_id += 1
        return f'Added todo: "{text}" with ID {todo.id}'

    @server.tool()
    def list_todos() -> str:
        """List all todo items."""
        if not todos:
            return "No todos found"

        todo_list = []
        for todo in todos:
            status = "✓" if todo.completed else "○"
            todo_list.append(f"{todo.id}: {todo.text} {status}")

        return "\n".join(todo_list)

    @server.tool()
    def complete_todo(id: int) -> str:
        """Mark a todo item as completed."""
        for todo in todos:
            if todo.id == id:
                todo.completed = True
                return f'Completed todo: "{todo.text}"'

        raise ValueError(f"Todo with ID {id} not found")

    # Store original handlers for testing
    server._original_handlers = {
        "add_todo": add_todo,
        "list_todos": list_todos,
        "complete_todo": complete_todo,
    }

    return server
