"""Logging functionality for MCPCat."""

import os
from datetime import datetime, timezone

from mcpcat.types import MCPCatOptions


# Initialize debug_mode from environment variable at module load time
_env_debug = os.getenv("MCPCAT_DEBUG_MODE")
if _env_debug is not None:
    debug_mode = _env_debug.lower() in ("true", "1", "yes", "on")
else:
    debug_mode = False


def set_debug_mode(value: bool) -> None:
    """Set the global debug_mode value."""
    global debug_mode
    debug_mode = value


def write_to_log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    log_entry = f"[{timestamp}] {message}\n"

    # Always use ~/mcpcat.log
    log_path = os.path.expanduser("~/mcpcat.log")

    try:
        if debug_mode:
            # Write to log file (no need to ensure directory exists for home directory)
            with open(log_path, "a") as f:
                f.write(log_entry)
    except Exception:
        # Silently fail - we don't want logging errors to break the server
        pass
