"""Logging functionality for MCPCat."""

import os
from datetime import datetime, timezone

from mcpcat.types import MCPCatOptions


debug_mode = False


def write_to_log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    log_entry = f"[{timestamp}] {message}\n"

    # Always use ~/mcpcat.log
    log_path = os.path.expanduser("~/mcpcat.log")

    try:
        global debug_mode
        debug_mode = (
            os.getenv("MCPCAT_DEBUG_MODE").lower()
            if os.getenv("MCPCAT_DEBUG_MODE") != None
            else str(debug_mode).lower()
        )
        if debug_mode == "true":
            # Write to log file (no need to ensure directory exists for home directory)
            with open(log_path, "a") as f:
                f.write(log_entry)
    except Exception:
        # Silently fail - we don't want logging errors to break the server
        pass
